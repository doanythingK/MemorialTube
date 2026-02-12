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


def _build_blurred_background(image_bgr: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    pil = Image.fromarray(image_bgr[:, :, ::-1], mode="RGB")
    w, h = pil.size
    s = max(target_w / w, target_h / h)
    cover_w = max(1, int(round(w * s)))
    cover_h = max(1, int(round(h * s)))
    cover = pil.resize((cover_w, cover_h), Image.Resampling.LANCZOS)

    left = (cover_w - target_w) // 2
    top = (cover_h - target_h) // 2
    cropped = cover.crop((left, top, left + target_w, top + target_h))
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=22))
    return np.array(blurred, dtype=np.uint8)[:, :, ::-1]


def _compose_center(background_bgr: np.ndarray, resized_bgr: np.ndarray, placement: Placement) -> np.ndarray:
    canvas = background_bgr.copy()
    y1, y2 = placement.y, placement.y + placement.height
    x1, x2 = placement.x, placement.x + placement.width
    canvas[y1:y2, x1:x2] = resized_bgr
    return canvas


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


def build_canvas_image(
    input_path: str,
    *,
    outpaint_adapter: OutpaintAdapter | None = None,
    animal_detector: AnimalDetector | None = None,
) -> CanvasBuildResult:
    target_w = settings.target_width
    target_h = settings.target_height
    strict = settings.strict_safety_checks

    source_bgr = _load_bgr(input_path)
    resized_bgr, placement = _resize_with_aspect(source_bgr, target_w, target_h)

    safe_background = _build_blurred_background(source_bgr, target_w, target_h)
    safe_canvas = _compose_center(safe_background, resized_bgr, placement)

    # Outpaint is only attempted on left/right gaps and only when content width is enough.
    if placement.width >= target_w or placement.width < settings.outpaint_min_width_for_generation:
        return CanvasBuildResult(
            image=safe_canvas,
            used_outpaint=False,
            fallback_applied=True,
            fallback_reason="outpaint skipped by width policy",
            safety_passed=True,
            safety_message="safe padding path",
        )

    base_for_generation = safe_canvas.copy()
    protected_mask, generation_mask = _make_masks(target_w, target_h, placement)

    adapter = outpaint_adapter or create_default_outpaint_adapter()
    detector = animal_detector or create_default_detector()
    last_reason = "unknown outpaint failure"
    attempts = max(1, settings.outpaint_max_attempts)

    for _attempt in range(1, attempts + 1):
        try:
            candidate = adapter.outpaint(base_for_generation, generation_mask)
        except Exception as exc:  # noqa: BLE001 - model adapter error path
            last_reason = f"outpaint execution failed: {exc}"
            continue

        protected_check = check_protected_region_unchanged(
            base_for_generation,
            candidate,
            protected_mask,
        )
        if not protected_check.passed:
            last_reason = protected_check.reason or "protected region safety check failed"
            continue

        # Deterministic placeholder adapter does not synthesize new entities.
        if not isinstance(adapter, MirrorOutpaintAdapter):
            animal_check = check_no_new_animals_in_generated_region(
                candidate,
                generation_mask,
                detector,
                strict_mode=strict,
            )
            if not animal_check.passed:
                last_reason = animal_check.reason or "new-animal safety check failed"
                continue

        return CanvasBuildResult(
            image=candidate,
            used_outpaint=True,
            fallback_applied=False,
            fallback_reason=None,
            safety_passed=True,
            safety_message="outpaint accepted",
        )

    return CanvasBuildResult(
        image=safe_canvas,
        used_outpaint=True,
        fallback_applied=True,
        fallback_reason=last_reason,
        safety_passed=False,
        safety_message="outpaint attempts exhausted, fallback applied",
    )


def run_canvas_job(input_path: str, output_path: str) -> CanvasBuildResult:
    result = build_canvas_image(input_path)
    _save_bgr(output_path, result.image)
    return result
