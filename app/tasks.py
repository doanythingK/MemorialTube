import subprocess
from pathlib import Path

from app import crud
from app.canvas.pipeline import run_canvas_job
from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models import JobStatus
from app.video.last_clip import build_last_clip
from app.video.render import build_final_render
from app.video.transition import build_transition_clip


@celery_app.task(name="app.tasks.run_test_render")
def run_test_render(job_id: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        crud.set_job_status(db, job_id, JobStatus.PROCESSING)

        cmd = [settings.ffmpeg_path, "-version"]
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or "ffmpeg command failed")

        first_line = (process.stdout or "").splitlines()
        result_message = first_line[0] if first_line else "ffmpeg check succeeded"

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
        crud.set_job_status(db, job_id, JobStatus.PROCESSING)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        result = run_canvas_job(input_path=input_path, output_path=output_path)

        message = (
            f"canvas done: outpaint={result.used_outpaint}, "
            f"fallback={result.fallback_applied}, "
            f"safety={result.safety_passed}, "
            f"reason={result.fallback_reason or 'none'}"
        )
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
        crud.set_job_status(db, job_id, JobStatus.PROCESSING)

        built = build_transition_clip(
            image_a_path=image_a_path,
            image_b_path=image_b_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )

        message = (
            f"transition done: duration={duration_seconds}s, "
            f"generative={built.used_generative}, "
            f"fallback={built.fallback_applied}, "
            f"safety={built.safety_passed}, "
            f"reason={built.fallback_reason or 'none'}, "
            f"output={built.output_path}"
        )
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
        crud.set_job_status(db, job_id, JobStatus.PROCESSING)

        built = build_last_clip(
            image_path=image_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            motion_style=motion_style,
        )

        message = (
            f"last clip done: duration={duration_seconds}s, "
            f"motion={motion_style}, output={built}"
        )
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
        crud.set_job_status(db, job_id, JobStatus.PROCESSING)

        built = build_final_render(
            clip_paths=clip_paths,
            output_path=output_path,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
        )
        message = (
            f"final render done: clips={len(clip_paths)}, "
            f"bgm={'yes' if bgm_path else 'no'}, output={built}"
        )
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
