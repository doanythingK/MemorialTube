import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app import crud
from app.canvas.pipeline import run_canvas_job
from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models import JobStatus, ProjectStatus
from app.pipeline.orchestrator import run_full_pipeline
from app.video.last_clip import build_last_clip
from app.video.render import build_final_render
from app.video.transition import build_transition_clip


class JobCanceledError(RuntimeError):
    pass


def _update_progress(
    db: Session,
    job_id: str,
    *,
    stage: str,
    progress: int,
    detail: str | None = None,
) -> None:
    crud.upsert_job_runtime(
        db,
        job_id,
        stage=stage,
        progress_percent=progress,
        detail_message=detail,
    )


def _ensure_not_canceled(db: Session, job_id: str) -> None:
    if crud.is_cancel_requested(db, job_id):
        crud.mark_job_canceled(db, job_id, reason="canceled by user")
        raise JobCanceledError("canceled by user")


def _begin_processing(db: Session, job_id: str) -> None:
    _ensure_not_canceled(db, job_id)
    crud.set_job_status(db, job_id, JobStatus.PROCESSING)


@celery_app.task(name="app.tasks.run_test_render")
def run_test_render(job_id: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="test_start", progress=5, detail="checking ffmpeg")
        _ensure_not_canceled(db, job_id)

        cmd = [settings.ffmpeg_path, "-version"]
        _update_progress(db, job_id, stage="test_exec", progress=60, detail="running ffmpeg -version")
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or "ffmpeg command failed")

        first_line = (process.stdout or "").splitlines()
        result_message = first_line[0] if first_line else "ffmpeg check succeeded"
        _update_progress(db, job_id, stage="test_done", progress=100, detail=result_message)

        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=result_message,
        )
        return {"job_id": job_id, "result": result_message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_canvas_render")
def run_canvas_render(job_id: str, input_path: str, output_path: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="canvas_start", progress=5, detail="starting canvas")
        _ensure_not_canceled(db, job_id)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        _update_progress(db, job_id, stage="canvas_generate", progress=45, detail="running outpainting/padding")
        result = run_canvas_job(input_path=input_path, output_path=output_path)
        _update_progress(db, job_id, stage="canvas_validate", progress=85, detail="running safety checks")
        _ensure_not_canceled(db, job_id)

        message = (
            f"canvas done: outpaint={result.used_outpaint}, "
            f"fallback={result.fallback_applied}, "
            f"safety={result.safety_passed}, "
            f"reason={result.fallback_reason or 'none'}"
        )
        _update_progress(db, job_id, stage="canvas_done", progress=100, detail=message)
        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=message,
        )
        return {"job_id": job_id, "result": message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_transition_render")
def run_transition_render(
    job_id: str,
    image_a_path: str,
    image_b_path: str,
    output_path: str,
    duration_seconds: int,
    prompt: str,
    negative_prompt: str | None = None,
) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="transition_start", progress=5, detail="starting transition")
        _ensure_not_canceled(db, job_id)

        _update_progress(db, job_id, stage="transition_generate", progress=45, detail="generating transition clip")
        built = build_transition_clip(
            image_a_path=image_a_path,
            image_b_path=image_b_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
        _update_progress(db, job_id, stage="transition_validate", progress=85, detail="running transition safety checks")
        _ensure_not_canceled(db, job_id)

        message = (
            f"transition done: duration={duration_seconds}s, "
            f"generative={built.used_generative}, "
            f"fallback={built.fallback_applied}, "
            f"safety={built.safety_passed}, "
            f"reason={built.fallback_reason or 'none'}, "
            f"output={built.output_path}"
        )
        _update_progress(db, job_id, stage="transition_done", progress=100, detail=message)
        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=message,
        )
        return {"job_id": job_id, "result": message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_last_clip_render")
def run_last_clip_render(
    job_id: str,
    image_path: str,
    output_path: str,
    duration_seconds: int,
    motion_style: str,
) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="last_clip_start", progress=5, detail="starting last clip")
        _ensure_not_canceled(db, job_id)

        _update_progress(db, job_id, stage="last_clip_generate", progress=60, detail="building standalone clip")
        built = build_last_clip(
            image_path=image_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            motion_style=motion_style,
        )
        _update_progress(db, job_id, stage="last_clip_finalize", progress=90, detail="finalizing last clip")
        _ensure_not_canceled(db, job_id)

        message = (
            f"last clip done: duration={duration_seconds}s, "
            f"motion={motion_style}, output={built}"
        )
        _update_progress(db, job_id, stage="last_clip_done", progress=100, detail=message)
        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=message,
        )
        return {"job_id": job_id, "result": message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_final_render")
def run_final_render(
    job_id: str,
    clip_paths: list[str],
    output_path: str,
    bgm_path: str | None = None,
    bgm_volume: float = 0.15,
) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="render_start", progress=5, detail="starting final render")
        _ensure_not_canceled(db, job_id)

        _update_progress(db, job_id, stage="render_concat", progress=45, detail="concatenating clips")
        built = build_final_render(
            clip_paths=clip_paths,
            output_path=output_path,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
        )
        _update_progress(db, job_id, stage="render_finalize", progress=90, detail="finalizing output")
        _ensure_not_canceled(db, job_id)
        message = (
            f"final render done: clips={len(clip_paths)}, "
            f"bgm={'yes' if bgm_path else 'no'}, output={built}"
        )
        _update_progress(db, job_id, stage="render_done", progress=100, detail=message)
        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=message,
        )
        return {"job_id": job_id, "result": message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_pipeline_render")
def run_pipeline_render(
    job_id: str,
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
    project_id: str | None = None,
) -> dict[str, str]:
    db = SessionLocal()
    try:
        _begin_processing(db, job_id)
        _update_progress(db, job_id, stage="pipeline_start", progress=1, detail="pipeline started")
        _ensure_not_canceled(db, job_id)

        def on_progress(stage: str, progress: int, detail: str | None) -> None:
            _update_progress(db, job_id, stage=stage, progress=progress, detail=detail)

        def check_canceled() -> None:
            _ensure_not_canceled(db, job_id)

        summary = run_full_pipeline(
            image_paths=image_paths,
            working_dir=working_dir,
            final_output_path=final_output_path,
            transition_duration_seconds=transition_duration_seconds,
            transition_prompt=transition_prompt,
            transition_negative_prompt=transition_negative_prompt,
            last_clip_duration_seconds=last_clip_duration_seconds,
            last_clip_motion_style=last_clip_motion_style,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            on_progress=on_progress,
            check_canceled=check_canceled,
        )

        message = (
            f"pipeline done: images={len(image_paths)}, "
            f"transitions={len(summary.transition_paths)}, "
            f"fallbacks={summary.fallback_count}, "
            f"safety_failed={summary.safety_failed_count}, "
            f"output={summary.final_output_path}"
        )
        _update_progress(db, job_id, stage="pipeline_done", progress=100, detail=message)
        crud.set_job_status(
            db,
            job_id,
            JobStatus.SUCCEEDED,
            result_message=message,
        )
        if project_id:
            try:
                crud.set_project_status(db, project_id, ProjectStatus.COMPLETED)
            except Exception:
                pass
        return {"job_id": job_id, "result": message}
    except Exception as exc:  # noqa: BLE001 - worker failure must be captured
        crud.set_job_status(db, job_id, JobStatus.FAILED, error_message=str(exc))
        if project_id:
            try:
                crud.set_project_status(db, project_id, ProjectStatus.FAILED)
            except Exception:
                pass
        raise
    finally:
        db.close()
