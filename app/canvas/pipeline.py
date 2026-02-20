from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from app.canvas.detector import AnimalDetector, create_default_detector
from app.canvas.outpaint import (
    MirrorOutpaintAdapter,
    OutpaintAdapter,
    create_default_outpaint_adapter,
)
from app.canvas.safety import (
    check_generation_boundary_continuity,
    check_generated_region_naturalness,
    check_no_new_animals_in_generated_region,
    check_protected_region_unchanged,
)
from app.canvas.types import CanvasBuildResult
from app.config import settings


@dataclass(slots=True)
class Placement:
    x: int
    y: int
    width: int
    height: int


def _load_bgr(path: str) -> np.ndarray:
    pil = Image.open(path).convert("RGB")
    rgb = np.array(pil, dtype=np.uint8)
    return rgb[:, :, ::-1]  # RGB -> BGR


def _save_bgr(path: str, image_bgr: np.ndarray) -> None:
    rgb = image_bgr[:, :, ::-1]
    Image.fromarray(rgb, mode="RGB").save(path)


def _resize_with_aspect(image_bgr: np.ndarray, target_w: int, target_h: int) -> tuple[np.ndarray, Placement]:
    h, w = image_bgr.shape[:2]
    s = min(target_w / w, target_h / h)
    w1 = max(1, int(round(w * s)))
    h1 = max(1, int(round(h * s)))

    resized = np.array(
        Image.fromarray(image_bgr[:, :, ::-1], mode="RGB").resize((w1, h1), Image.Resampling.LANCZOS)
    )[:, :, ::-1]

    x = (target_w - w1) // 2
    y = (target_h - h1) // 2
    return resized, Placement(x=x, y=y, width=w1, height=h1)


def _build_safe_background(
    image_bgr: np.ndarray,
    resized_bgr: np.ndarray,
    placement: Placement,
    target_w: int,
    target_h: int,
) -> np.ndarray:
    style = settings.canvas_background_style.lower().strip()
    pad_left = placement.x
    pad_right = target_w - (placement.x + placement.width)
    pad_top = placement.y
    pad_bottom = target_h - (placement.y + placement.height)

    # Reflect padding is opt-in only; default style should avoid mirrored look.
    if (
        style == "reflect"
        and pad_top == 0
        and pad_bottom == 0
        and (pad_left > 0 or pad_right > 0)
    ):
        pad_mode = "reflect"
        if placement.width <= 1 or pad_left >= placement.width or pad_right >= placement.width:
            pad_mode = "edge"
        safe = np.pad(
            resized_bgr,
            ((0, 0), (pad_left, pad_right), (0, 0)),
            mode=pad_mode,
        )
        if safe.shape[1] == target_w and safe.shape[0] == target_h:
            return safe

    pil = Image.fromarray(image_bgr[:, :, ::-1], mode="RGB")
    w, h = pil.size
    s = max(target_w / w, target_h / h)
    cover_w = max(1, int(round(w * s)))
    cover_h = max(1, int(round(h * s)))
    cover = pil.resize((cover_w, cover_h), Image.Resampling.LANCZOS)

    left = (cover_w - target_w) // 2
    top = (cover_h - target_h) // 2
    cropped = cover.crop((left, top, left + target_w, top + target_h))

    if style == "blur":
        radius = max(0, int(settings.canvas_background_blur_radius))
        if radius > 0:
            cropped = cropped.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(cropped, dtype=np.uint8)[:, :, ::-1]


def _compose_center(background_bgr: np.ndarray, resized_bgr: np.ndarray, placement: Placement) -> np.ndarray:
    canvas = background_bgr.copy()
    y1, y2 = placement.y, placement.y + placement.height
    x1, x2 = placement.x, placement.x + placement.width
    canvas[y1:y2, x1:x2] = resized_bgr

    blend_px = max(0, int(settings.canvas_edge_blend_px))
    if blend_px == 0:
        return canvas

    h, w = canvas.shape[:2]
    if x1 <= 0 and x2 >= w:
        return canvas

    alpha = np.zeros((h, w), dtype=np.float32)
    alpha[y1:y2, x1:x2] = 1.0

    if x1 > 0:
        b = min(blend_px, x1, max(1, placement.width // 2))
        start = x1 - b
        end = x1 + b
        if end > start:
            grad = np.linspace(0.0, 1.0, end - start, endpoint=True, dtype=np.float32)
            alpha[y1:y2, start:end] = grad[None, :]

    if x2 < w:
        b = min(blend_px, w - x2, max(1, placement.width // 2))
        start = x2 - b
        end = x2 + b
        if end > start:
            grad = np.linspace(1.0, 0.0, end - start, endpoint=True, dtype=np.float32)
            alpha[y1:y2, start:end] = grad[None, :]

    alpha_3d = alpha[:, :, None]
    blended = (
        canvas.astype(np.float32) * alpha_3d
        + background_bgr.astype(np.float32) * (1.0 - alpha_3d)
    )
    return np.clip(np.round(blended), 0, 255).astype(np.uint8)


def _make_masks(target_w: int, target_h: int, placement: Placement) -> tuple[np.ndarray, np.ndarray]:
    # Protected region: original image placement area.
    protected = np.zeros((target_h, target_w), dtype=np.uint8)
    protected[
        placement.y : placement.y + placement.height,
        placement.x : placement.x + placement.width,
    ] = 255

    # Generation region: only left/right paddings (top/bottom excluded by policy).
    generation = np.zeros((target_h, target_w), dtype=np.uint8)
    if placement.x > 0:
        generation[:, : placement.x] = 255
    right_start = placement.x + placement.width
    if right_start < target_w:
        generation[:, right_start:] = 255
    return protected, generation


def _preserve_protected_region(
    base_image_bgr: np.ndarray,
    candidate_image_bgr: np.ndarray,
    protected_mask: np.ndarray,
) -> np.ndarray:
    preserved = candidate_image_bgr.copy()
    region = protected_mask > 0
    if region.any():
        preserved[region] = base_image_bgr[region]
    return preserved


def _harmonize_generated_region(
    candidate_image_bgr: np.ndarray,
    safe_canvas_bgr: np.ndarray,
    generation_mask: np.ndarray,
    placement: Placement,
) -> np.ndarray:
    if generation_mask.shape != candidate_image_bgr.shape[:2]:
        return candidate_image_bgr

    h, w = generation_mask.shape
    right_start = placement.x + placement.width
    left_width = max(0, placement.x)
    right_width = max(0, w - right_start)

    alpha = np.zeros((h, w), dtype=np.float32)

    # Blend more near the protected boundary and less toward the outer edge.
    if left_width > 0:
        left_ramp = np.linspace(0.20, 0.50, left_width, endpoint=True, dtype=np.float32)
        alpha[:, :left_width] = left_ramp[None, :]

    if right_width > 0:
        right_ramp = np.linspace(0.50, 0.20, right_width, endpoint=True, dtype=np.float32)
        alpha[:, right_start:] = right_ramp[None, :]

    region = generation_mask > 0
    if not region.any():
        return candidate_image_bgr

    alpha *= region.astype(np.float32)
    a3 = alpha[:, :, None]
    mixed = (
        candidate_image_bgr.astype(np.float32) * (1.0 - a3)
        + safe_canvas_bgr.astype(np.float32) * a3
    )
    return np.clip(np.round(mixed), 0, 255).astype(np.uint8)


def build_canvas_image(
    input_path: str,
    *,
    outpaint_adapter: OutpaintAdapter | None = None,
    animal_detector: AnimalDetector | None = None,
    fast_mode: bool = False,
    enable_animal_detection: bool = True,
) -> CanvasBuildResult:
    target_w = settings.target_width
    target_h = settings.target_height
    strict = settings.strict_safety_checks

    source_bgr = _load_bgr(input_path)
    resized_bgr, placement = _resize_with_aspect(source_bgr, target_w, target_h)

    safe_background = _build_safe_background(
        source_bgr,
        resized_bgr,
        placement,
        target_w,
        target_h,
    )
    safe_canvas = _compose_center(safe_background, resized_bgr, placement)

    # Outpaint is only attempted on left/right gaps and only when content width is enough.
    if placement.width >= target_w or placement.width < settings.outpaint_min_width_for_generation:
        return CanvasBuildResult(
            image=safe_canvas,
            used_outpaint=False,
            adapter_name="none",
            fallback_applied=True,
            fallback_reason="outpaint skipped by width policy",
            safety_passed=True,
            safety_message="safe padding path",
        )

    base_for_generation = safe_canvas.copy()
    protected_mask, generation_mask = _make_masks(target_w, target_h, placement)

    adapter = outpaint_adapter or create_default_outpaint_adapter()
    adapter_name = type(adapter).__name__
    detector: AnimalDetector | None = animal_detector
    last_reason = "unknown outpaint failure"
    attempts = 1 if fast_mode else max(1, settings.outpaint_max_attempts)
    outpaint_steps = 12 if fast_mode else settings.outpaint_num_inference_steps

    for _attempt in range(1, attempts + 1):
        try:
            candidate = adapter.outpaint(
                base_for_generation,
                generation_mask,
                num_inference_steps=outpaint_steps,
                fast_mode=fast_mode,
            )
        except Exception as exc:  # noqa: BLE001 - model adapter error path
            last_reason = f"outpaint execution failed: {exc}"
            continue

        # Preserve the original subject region exactly before safety checks.
        candidate = _preserve_protected_region(
            base_for_generation,
            candidate,
            protected_mask,
        )

        if fast_mode:
            candidate = _harmonize_generated_region(
                candidate,
                safe_canvas,
                generation_mask,
                placement,
            )

        try:
            protected_check = check_protected_region_unchanged(
                base_for_generation,
                candidate,
                protected_mask,
            )
        except ValueError as exc:
            last_reason = f"protected region safety check error: {exc}"
            continue
        if not protected_check.passed:
            last_reason = protected_check.reason or "protected region safety check failed"
            continue

        # Deterministic placeholder adapter does not synthesize new entities.
        if not isinstance(adapter, MirrorOutpaintAdapter):
            if enable_animal_detection:
                if detector is None:
                    detector = create_default_detector()
                animal_check = check_no_new_animals_in_generated_region(
                    candidate,
                    generation_mask,
                    detector,
                    strict_mode=strict,
                )
                if not animal_check.passed:
                    last_reason = animal_check.reason or "new-animal safety check failed"
                    continue

            boundary_check = check_generation_boundary_continuity(
                candidate,
                protected_mask,
                generation_mask,
            )
            if not boundary_check.passed:
                last_reason = boundary_check.reason or "generation boundary safety check failed"
                continue

            naturalness_check = check_generated_region_naturalness(
                candidate,
                protected_mask,
                generation_mask,
            )
            if not naturalness_check.passed:
                last_reason = naturalness_check.reason or "generated region naturalness check failed"
                continue

        if isinstance(adapter, MirrorOutpaintAdapter):
            return CanvasBuildResult(
                image=safe_canvas,
                used_outpaint=False,
                adapter_name=adapter_name,
                fallback_applied=True,
                fallback_reason=(
                    "mirror adapter selected; forced safe background fallback "
                    "(generative outpaint unavailable)"
                ),
                safety_passed=True,
                safety_message="safe fallback applied (mirror output blocked)",
            )

        return CanvasBuildResult(
            image=candidate,
            used_outpaint=True,
            adapter_name=adapter_name,
            fallback_applied=False,
            fallback_reason=None,
            safety_passed=True,
            safety_message="outpaint accepted",
        )

    return CanvasBuildResult(
        image=safe_canvas,
        used_outpaint=True,
        adapter_name=adapter_name,
        fallback_applied=True,
        fallback_reason=last_reason,
        safety_passed=False,
        safety_message="outpaint attempts exhausted, fallback applied",
    )


def run_canvas_job(
    input_path: str,
    output_path: str,
    *,
    fast_mode: bool = False,
    enable_animal_detection: bool = True,
) -> CanvasBuildResult:
    result = build_canvas_image(
        input_path,
        fast_mode=fast_mode,
        enable_animal_detection=enable_animal_detection,
    )
    _save_bgr(output_path, result.image)
    return result
