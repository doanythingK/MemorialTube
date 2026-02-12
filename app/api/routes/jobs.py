from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.models import JobStatus
from app.schemas import (
    CanvasJobCreateRequest,
    JobCreateRequest,
    JobEnqueueResponse,
    JobResponse,
    LastClipJobCreateRequest,
    RenderJobCreateRequest,
    TransitionJobCreateRequest,
)
from app.tasks import (
    run_canvas_render,
    run_final_render,
    run_last_clip_render,
    run_test_render,
    run_transition_render,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/test", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_test_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type=payload.job_type)

    try:
        async_result = run_test_render.delay(job.id)
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/canvas", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_canvas_job(
    payload: CanvasJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type="canvas")

    try:
        async_result = run_canvas_render.delay(job.id, payload.input_path, payload.output_path)
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/transition", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_transition_job(
    payload: TransitionJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type="transition")

    try:
        async_result = run_transition_render.delay(
            job.id,
            payload.image_a_path,
            payload.image_b_path,
            payload.output_path,
            payload.duration_seconds,
            payload.prompt,
            payload.negative_prompt,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/last-clip", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_last_clip_job(
    payload: LastClipJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type="last_clip")

    try:
        async_result = run_last_clip_render.delay(
            job.id,
            payload.image_path,
            payload.output_path,
            payload.duration_seconds,
            payload.motion_style,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.post("/render", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_render_job(
    payload: RenderJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    job = crud.create_job(db, job_type="render")

    try:
        async_result = run_final_render.delay(
            job.id,
            payload.clip_paths,
            payload.output_path,
            payload.bgm_path,
            payload.bgm_volume,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_job_status(db, job.id, JobStatus.FAILED, error_message=str(exc))
        raise HTTPException(status_code=500, detail="Failed to enqueue task") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[JobResponse])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[JobResponse]:
    return crud.list_jobs(db, limit=limit)
