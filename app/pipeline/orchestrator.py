from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.canvas.pipeline import run_canvas_job
from app.video.last_clip import build_last_clip
from app.video.render import build_final_render
from app.video.transition import build_transition_clip


@dataclass(slots=True)
class PipelineRunSummary:
    final_output_path: str
    canvas_paths: list[str]
    transition_paths: list[str]
    last_clip_path: str
    fallback_count: int
    canvas_fallback_count: int
    transition_fallback_count: int
    safety_failed_count: int


def _require_files(paths: list[str]) -> None:
    for p in paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"input image not found: {p}")


def run_full_pipeline(
    *,
    image_paths: list[str],
    working_dir: str,
    final_output_path: str,
    transition_duration_seconds: int,
    transition_prompt: str,
    transition_negative_prompt: str | None,
    last_clip_duration_seconds: int,
    last_clip_motion_style: str,
    bgm_path: str | None,
    bgm_volume: float,
) -> PipelineRunSummary:
    if not image_paths:
        raise ValueError("image_paths must not be empty")
    if not transition_prompt.strip():
        raise ValueError("transition_prompt is required")

    _require_files(image_paths)

    root = Path(working_dir)
    canvas_dir = root / "canvas"
    transition_dir = root / "transitions"
    last_dir = root / "last"
    render_dir = root / "render"
    for d in (canvas_dir, transition_dir, last_dir, render_dir):
        d.mkdir(parents=True, exist_ok=True)

    canvas_paths: list[str] = []
    transition_paths: list[str] = []
    fallback_count = 0
    canvas_fallback_count = 0
    transition_fallback_count = 0
    safety_failed_count = 0

    # 1) Normalize/extend each image to target canvas.
    for idx, img_path in enumerate(image_paths):
        out_path = canvas_dir / f"canvas_{idx:04d}.jpg"
        canvas_result = run_canvas_job(img_path, str(out_path))
        canvas_paths.append(str(out_path))

        if canvas_result.fallback_applied:
            fallback_count += 1
            canvas_fallback_count += 1
        if not canvas_result.safety_passed:
            safety_failed_count += 1

    # 2) Build transitions between adjacent images.
    if len(canvas_paths) >= 2:
        for idx in range(len(canvas_paths) - 1):
            out_clip = transition_dir / f"transition_{idx:04d}.mp4"
            t_result = build_transition_clip(
                image_a_path=canvas_paths[idx],
                image_b_path=canvas_paths[idx + 1],
                output_path=str(out_clip),
                duration_seconds=transition_duration_seconds,
                prompt=transition_prompt,
                negative_prompt=transition_negative_prompt,
            )
            transition_paths.append(t_result.output_path)
            if t_result.fallback_applied:
                fallback_count += 1
                transition_fallback_count += 1
            if not t_result.safety_passed:
                safety_failed_count += 1

    # 3) Build last standalone clip using last image.
    last_source = canvas_paths[-1]
    last_clip_path = str(last_dir / "last_clip.mp4")
    build_last_clip(
        image_path=last_source,
        output_path=last_clip_path,
        duration_seconds=last_clip_duration_seconds,
        motion_style=last_clip_motion_style,
    )

    # 4) Final render with transitions + last clip.
    all_clips = [*transition_paths, last_clip_path]
    final_path = build_final_render(
        clip_paths=all_clips,
        output_path=final_output_path,
        bgm_path=bgm_path,
        bgm_volume=bgm_volume,
    )

    return PipelineRunSummary(
        final_output_path=final_path,
        canvas_paths=canvas_paths,
        transition_paths=transition_paths,
        last_clip_path=last_clip_path,
        fallback_count=fallback_count,
        canvas_fallback_count=canvas_fallback_count,
        transition_fallback_count=transition_fallback_count,
        safety_failed_count=safety_failed_count,
    )
