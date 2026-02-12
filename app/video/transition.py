from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageFilter

from app.canvas.detector import AnimalDetector, create_default_detector
from app.canvas.safety import check_protected_region_unchanged
from app.config import settings

ALLOWED_TRANSITION_DURATIONS = {6, 10}


@dataclass(slots=True)
class TransitionBuildResult:
    output_path: str
    used_generative: bool
    fallback_applied: bool
    fallback_reason: str | None
    safety_passed: bool
    safety_message: str


class GenerativeTransitionAdapter(Protocol):
    @property
    def available(self) -> bool:
        ...

    def generate_frame(
        self,
        base_frame_bgr: np.ndarray,
        prompt: str,
        negative_prompt: str | None,
    ) -> np.ndarray:
        ...


class NullGenerativeTransitionAdapter:
    @property
    def available(self) -> bool:
        return False

    def generate_frame(
        self,
        base_frame_bgr: np.ndarray,
        prompt: str,
        negative_prompt: str | None,
    ) -> np.ndarray:
        _ = prompt, negative_prompt
        return base_frame_bgr


class DiffusersImage2ImageTransitionAdapter:
    def __init__(self) -> None:
        import torch  # noqa: PLC0415 - optional dependency
        from diffusers import AutoPipelineForImage2Image  # noqa: PLC0415 - optional dependency

        self._torch = torch
        device = settings.transition_device.lower().strip()
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = device

        dtype = torch.float16 if device == "cuda" else torch.float32
        self._pipe = AutoPipelineForImage2Image.from_pretrained(
            settings.transition_model_id,
            torch_dtype=dtype,
        )
        self._pipe.to(device)
        self._pipe.set_progress_bar_config(disable=True)
        if device == "cuda":
            self._pipe.enable_attention_slicing()

    @property
    def available(self) -> bool:
        return True

    def generate_frame(
        self,
        base_frame_bgr: np.ndarray,
        prompt: str,
        negative_prompt: str | None,
    ) -> np.ndarray:
        gen_w = max(64, int(settings.transition_generation_width))
        gen_h = max(64, int(settings.transition_generation_height))

        base_rgb = base_frame_bgr[:, :, ::-1]
        base_pil = Image.fromarray(base_rgb, mode="RGB").resize(
            (gen_w, gen_h),
            Image.Resampling.LANCZOS,
        )

        kwargs: dict[str, object] = {
            "prompt": prompt,
            "image": base_pil,
            "strength": settings.transition_strength,
            "guidance_scale": settings.transition_guidance_scale,
            "num_inference_steps": settings.transition_num_inference_steps,
        }
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        result = self._pipe(**kwargs).images[0]
        result = result.resize(
            (settings.target_width, settings.target_height),
            Image.Resampling.LANCZOS,
        )
        out_rgb = np.array(result, dtype=np.uint8)
        return out_rgb[:, :, ::-1]


@lru_cache(maxsize=1)
def create_transition_adapter() -> GenerativeTransitionAdapter:
    provider = settings.transition_provider.lower().strip()

    if provider == "classic":
        return NullGenerativeTransitionAdapter()

    if provider in {"diffusers", "auto"}:
        try:
            return DiffusersImage2ImageTransitionAdapter()
        except Exception:  # noqa: BLE001 - optional dependency/model load failure
            if provider == "diffusers":
                raise

    return NullGenerativeTransitionAdapter()


def _load_and_normalize(path: str) -> np.ndarray:
    src = Image.open(path).convert("RGB")
    w, h = src.size
    s = min(settings.target_width / w, settings.target_height / h)
    w1 = max(1, int(round(w * s)))
    h1 = max(1, int(round(h * s)))

    fg = src.resize((w1, h1), Image.Resampling.LANCZOS)

    # Safe background pad policy.
    cover_s = max(settings.target_width / w, settings.target_height / h)
    cw = max(1, int(round(w * cover_s)))
    ch = max(1, int(round(h * cover_s)))
    bg = src.resize((cw, ch), Image.Resampling.LANCZOS)
    left = (cw - settings.target_width) // 2
    top = (ch - settings.target_height) // 2
    bg = bg.crop((left, top, left + settings.target_width, top + settings.target_height))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=22))

    canvas = np.array(bg, dtype=np.uint8)
    x = (settings.target_width - w1) // 2
    y = (settings.target_height - h1) // 2
    canvas[y : y + h1, x : x + w1] = np.array(fg, dtype=np.uint8)
    return canvas[:, :, ::-1]  # RGB -> BGR


def _blend(a_bgr: np.ndarray, b_bgr: np.ndarray, alpha: float) -> np.ndarray:
    alpha = min(1.0, max(0.0, alpha))
    mixed = (a_bgr.astype(np.float32) * (1.0 - alpha)) + (b_bgr.astype(np.float32) * alpha)
    return np.clip(mixed, 0, 255).astype(np.uint8)


def _sample_indices(total_frames: int, step: int) -> list[int]:
    if total_frames <= 2:
        return []
    step = max(1, step)
    indices = list(range(1, total_frames - 1, step))
    last_mid = total_frames - 2
    if last_mid not in indices:
        indices.append(last_mid)
    return sorted(set(indices))


def _animal_count(detector: AnimalDetector, frame_bgr: np.ndarray, strict: bool) -> tuple[int, str | None]:
    if not detector.available:
        if strict:
            return -1, "animal detector unavailable in strict mode"
        return 0, None
    detections = detector.detect_animals(frame_bgr)
    return len(detections), None


def _validate_transition_safety(
    frames: list[np.ndarray],
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    detector: AnimalDetector,
) -> tuple[bool, str | None]:
    if not frames:
        return False, "frames are empty"

    full_mask = np.full((settings.target_height, settings.target_width), 255, dtype=np.uint8)
    start_check = check_protected_region_unchanged(frame_a, frames[0], full_mask, max_changed_ratio=0.0)
    if not start_check.passed:
        return False, f"first frame mismatch: {start_check.reason}"

    end_check = check_protected_region_unchanged(frame_b, frames[-1], full_mask, max_changed_ratio=0.0)
    if not end_check.passed:
        return False, f"last frame mismatch: {end_check.reason}"

    strict = settings.strict_safety_checks
    base_a, err = _animal_count(detector, frame_a, strict)
    if err:
        return False, err
    base_b, err = _animal_count(detector, frame_b, strict)
    if err:
        return False, err

    baseline = max(base_a, base_b)
    allowed = max(0, int(settings.transition_allowed_extra_animals))

    for idx in _sample_indices(len(frames), settings.transition_safety_sample_step):
        count, err = _animal_count(detector, frames[idx], strict)
        if err:
            return False, err
        if count > baseline + allowed:
            return False, (
                f"extra animal detected on frame {idx}: count={count}, "
                f"baseline={baseline}, allowed={allowed}"
            )

    return True, None


def _write_frames_to_video(frames: list[np.ndarray], output_path: str) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="transition_frames_") as tmp_dir:
        tmp = Path(tmp_dir)
        for i, frame_bgr in enumerate(frames):
            frame_rgb = frame_bgr[:, :, ::-1]
            Image.fromarray(frame_rgb, mode="RGB").save(tmp / f"frame_{i:06d}.png")

        cmd = [
            settings.ffmpeg_path,
            "-y",
            "-framerate",
            str(settings.target_fps),
            "-i",
            str(tmp / "frame_%06d.png"),
            "-r",
            str(settings.target_fps),
            "-pix_fmt",
            settings.output_pixel_format,
            "-c:v",
            settings.output_video_codec,
            str(out),
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or "ffmpeg frame-to-video failed")

    return str(out)


def _build_classic_transition_clip(
    image_a_path: str,
    image_b_path: str,
    output_path: str,
    duration_seconds: int,
) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    xfade_duration = 1.0
    xfade_offset = max(0.0, float(duration_seconds) - xfade_duration)
    filter_complex = (
        f"[0:v]scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2,format={settings.output_pixel_format},fps={settings.target_fps}[v0];"
        f"[1:v]scale={settings.target_width}:{settings.target_height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.target_width}:{settings.target_height}:(ow-iw)/2:(oh-ih)/2,format={settings.output_pixel_format},fps={settings.target_fps}[v1];"
        f"[v0][v1]xfade=transition=fade:duration={xfade_duration}:offset={xfade_offset},"
        f"format={settings.output_pixel_format}"
    )

    cmd = [
        settings.ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-t",
        str(duration_seconds),
        "-i",
        image_a_path,
        "-loop",
        "1",
        "-t",
        str(duration_seconds),
        "-i",
        image_b_path,
        "-filter_complex",
        filter_complex,
        "-t",
        str(duration_seconds),
        "-r",
        str(settings.target_fps),
        "-pix_fmt",
        settings.output_pixel_format,
        "-c:v",
        settings.output_video_codec,
        str(out),
    ]
    process = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "ffmpeg classic transition build failed")
    return str(out)


def build_transition_clip(
    image_a_path: str,
    image_b_path: str,
    output_path: str,
    duration_seconds: int,
    *,
    prompt: str,
    negative_prompt: str | None = None,
) -> TransitionBuildResult:
    if duration_seconds not in ALLOWED_TRANSITION_DURATIONS:
        raise ValueError("duration_seconds must be one of: 6, 10")
    if not prompt.strip():
        raise ValueError("prompt is required for generative transition")

    frame_a = _load_and_normalize(image_a_path)
    frame_b = _load_and_normalize(image_b_path)

    total_frames = max(2, int(duration_seconds * settings.target_fps))
    adapter = create_transition_adapter()
    detector = create_default_detector()

    # If explicit classic mode, bypass generative attempts.
    if settings.transition_provider.lower().strip() == "classic":
        built = _build_classic_transition_clip(
            image_a_path=image_a_path,
            image_b_path=image_b_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
        )
        return TransitionBuildResult(
            output_path=built,
            used_generative=False,
            fallback_applied=True,
            fallback_reason="classic provider configured",
            safety_passed=True,
            safety_message="classic transition path",
        )

    last_reason = "unknown generative transition failure"
    attempts = max(1, int(settings.transition_max_attempts))

    for _attempt in range(1, attempts + 1):
        if not adapter.available:
            last_reason = "generative adapter unavailable"
            continue

        try:
            frames: list[np.ndarray] = []
            gen_step = max(1, int(settings.transition_generation_step))
            for idx in range(total_frames):
                alpha = idx / (total_frames - 1)
                base = _blend(frame_a, frame_b, alpha)
                if idx == 0:
                    frame = frame_a.copy()
                elif idx == total_frames - 1:
                    frame = frame_b.copy()
                elif idx % gen_step != 0:
                    # Keep runtime bounded: use blended frame between generated keyframes.
                    frame = base
                else:
                    frame = adapter.generate_frame(base, prompt=prompt, negative_prompt=negative_prompt)
                frames.append(frame)

            # Hard enforce first/last exactness.
            frames[0] = frame_a.copy()
            frames[-1] = frame_b.copy()

            safety_ok, safety_reason = _validate_transition_safety(frames, frame_a, frame_b, detector)
            if not safety_ok:
                last_reason = safety_reason or "transition safety check failed"
                continue

            built = _write_frames_to_video(frames, output_path)
            return TransitionBuildResult(
                output_path=built,
                used_generative=True,
                fallback_applied=False,
                fallback_reason=None,
                safety_passed=True,
                safety_message="generative transition accepted",
            )
        except Exception as exc:  # noqa: BLE001 - generation/runtime failure
            last_reason = str(exc)
            continue

    built = _build_classic_transition_clip(
        image_a_path=image_a_path,
        image_b_path=image_b_path,
        output_path=output_path,
        duration_seconds=duration_seconds,
    )
    return TransitionBuildResult(
        output_path=built,
        used_generative=True,
        fallback_applied=True,
        fallback_reason=last_reason,
        safety_passed=False,
        safety_message="generative attempts exhausted, classic fallback applied",
    )
