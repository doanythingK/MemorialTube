from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.models import ProjectStatus
from app.security.path_guard import ensure_safe_input_path, ensure_safe_output_path
from app.schemas import (
    AssetResponse,
    JobEnqueueResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectRunRequest,
)
from app.storage.local import save_project_asset_file
from app.tasks import run_pipeline_render


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = crud.create_project(
        db,
        name=payload.name,
        transition_duration_seconds=payload.transition_duration_seconds,
        transition_prompt=payload.transition_prompt,
        transition_negative_prompt=payload.transition_negative_prompt,
        last_clip_duration_seconds=payload.last_clip_duration_seconds,
        last_clip_motion_style=payload.last_clip_motion_style,
        bgm_path=payload.bgm_path,
        bgm_volume=payload.bgm_volume,
        final_output_path=payload.final_output_path,
    )
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ProjectResponse]:
    return crud.list_projects(db, limit=limit)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/{project_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    order_index: int = Form(0),
    db: Session = Depends(get_db),
) -> AssetResponse:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        file_path, width, height, safe_name = save_project_asset_file(project_id, file)
    except Exception as exc:  # noqa: BLE001 - upload/decoding errors
        raise HTTPException(status_code=400, detail=f"Failed to save asset: {exc}") from exc
    finally:
        file.file.close()

    asset = crud.add_asset(
        db,
        project_id=project_id,
        order_index=order_index,
        file_name=safe_name,
        file_path=file_path,
        width=width,
        height=height,
    )
    return asset


@router.get("/{project_id}/assets", response_model=list[AssetResponse])
def list_assets(project_id: str, db: Session = Depends(get_db)) -> list[AssetResponse]:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.list_assets_by_project(db, project_id)


@router.post("/{project_id}/run", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def run_project_pipeline(
    project_id: str,
    payload: ProjectRunRequest,
    db: Session = Depends(get_db),
) -> JobEnqueueResponse:
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    assets = crud.list_assets_by_project(db, project_id)
    if len(assets) == 0:
        raise HTTPException(status_code=400, detail="No assets uploaded")

    try:
        image_paths = [ensure_safe_input_path(a.file_path) for a in assets]
        raw_work_dir = payload.working_dir or str(Path("data/work") / project_id)
        working_marker = ensure_safe_output_path(str(Path(raw_work_dir) / ".path_check"))
        work_dir = str(Path(working_marker).parent)
        final_output_path = ensure_safe_output_path(
            payload.final_output_path or project.final_output_path or str(
                Path("data/output") / f"{project_id}_final.mp4"
            )
        )
        bgm_path = ensure_safe_input_path(project.bgm_path) if project.bgm_path else None
    except Exception as exc:  # noqa: BLE001 - validation path
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = crud.create_job(db, job_type="pipeline_project")
    crud.set_project_status(db, project_id, ProjectStatus.RUNNING)

    try:
        async_result = run_pipeline_render.delay(
            job.id,
            image_paths,
            work_dir,
            final_output_path,
            project.transition_duration_seconds,
            project.transition_prompt,
            project.transition_negative_prompt,
            project.last_clip_duration_seconds,
            project.last_clip_motion_style,
            bgm_path,
            project.bgm_volume,
            project_id,
        )
    except Exception as exc:  # noqa: BLE001 - broker error path
        crud.set_project_status(db, project_id, ProjectStatus.FAILED)
        raise HTTPException(status_code=500, detail="Failed to enqueue project pipeline") from exc

    return JobEnqueueResponse(job_id=job.id, task_id=async_result.id, status=job.status)
