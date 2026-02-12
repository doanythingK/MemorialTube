from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    on_progress: Callable[[str, int, str | None], None] | None = None,
    check_canceled: Callable[[], None] | None = None,
) -> PipelineRunSummary:
    if not image_paths:
        raise ValueError("image_paths must not be empty")
    if not transition_prompt.strip():
        raise ValueError("transition_prompt is required")

    _require_files(image_paths)

    def _emit(stage: str, progress: int, detail: str | None = None) -> None:
        if on_progress is not None:
            on_progress(stage, progress, detail)

    def _check() -> None:
        if check_canceled is not None:
            check_canceled()

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

    _emit("pipeline_prepare", 1, "starting pipeline")
    _check()

    # 1) Normalize/extend each image to target canvas.
    total_images = len(image_paths)
    _emit("canvas_start", 5, f"canvas start: {total_images} image(s)")
    for idx, img_path in enumerate(image_paths):
        _check()
        canvas_progress = 6 + int(((idx) / max(1, total_images)) * 33)
        _emit("canvas", canvas_progress, f"canvas {idx + 1}/{total_images}")
        out_path = canvas_dir / f"canvas_{idx:04d}.jpg"
        canvas_result = run_canvas_job(img_path, str(out_path))
        canvas_paths.append(str(out_path))

        if canvas_result.fallback_applied:
            fallback_count += 1
            canvas_fallback_count += 1
        if not canvas_result.safety_passed:
            safety_failed_count += 1
    _emit("canvas_done", 40, f"canvas done: {len(canvas_paths)} image(s)")

    # 2) Build transitions between adjacent images.
    if len(canvas_paths) >= 2:
        total_transitions = len(canvas_paths) - 1
        _emit("transition_start", 45, f"transition start: {total_transitions} clip(s)")
        for idx in range(total_transitions):
            _check()
            trans_progress = 46 + int(((idx) / max(1, total_transitions)) * 28)
            _emit("transition", trans_progress, f"transition {idx + 1}/{total_transitions}")
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
        _emit("transition_done", 75, f"transition done: {len(transition_paths)} clip(s)")
    else:
        _emit("transition_skipped", 75, "transition skipped: single image")

    # 3) Build last standalone clip using last image.
    _check()
    _emit("last_clip_start", 82, "building last clip")
    last_source = canvas_paths[-1]
    last_clip_path = str(last_dir / "last_clip.mp4")
    build_last_clip(
        image_path=last_source,
        output_path=last_clip_path,
        duration_seconds=last_clip_duration_seconds,
        motion_style=last_clip_motion_style,
    )
    _emit("last_clip_done", 90, "last clip completed")

    # 4) Final render with transitions + last clip.
    _check()
    _emit("render_start", 92, "building final render")
    all_clips = [*transition_paths, last_clip_path]
    final_path = build_final_render(
        clip_paths=all_clips,
        output_path=final_output_path,
        bgm_path=bgm_path,
        bgm_volume=bgm_volume,
    )
    _emit("render_done", 99, "final render completed")
    _emit("completed", 100, "pipeline completed")

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
