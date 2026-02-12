from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Job, JobRuntime, JobStatus, Project, ProjectRun, ProjectStatus


def create_job(db: Session, job_type: str) -> Job:
    job = Job(job_type=job_type, status=JobStatus.QUEUED)
    db.add(job)
    db.commit()
    db.refresh(job)
    runtime = JobRuntime(
        job_id=job.id,
        stage="queued",
        progress_percent=0,
        detail_message="queued",
        cancel_requested=False,
    )
    db.add(runtime)
    db.commit()
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


def get_job_runtime(db: Session, job_id: str) -> JobRuntime | None:
    return db.get(JobRuntime, job_id)


def list_job_runtimes(db: Session, job_ids: list[str]) -> dict[str, JobRuntime]:
    if not job_ids:
        return {}
    stmt = select(JobRuntime).where(JobRuntime.job_id.in_(job_ids))
    rows = list(db.scalars(stmt))
    return {row.job_id: row for row in rows}


def list_jobs(db: Session, limit: int = 20) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def set_job_status(
    db: Session,
    job_id: str,
    status: JobStatus,
    *,
    error_message: str | None = None,
    result_message: str | None = None,
) -> Job:
    job = get_job(db, job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    job.status = status
    if error_message is not None:
        job.error_message = error_message
    if result_message is not None:
        job.result_message = result_message

    db.add(job)
    db.commit()
    db.refresh(job)

    runtime = get_job_runtime(db, job_id)
    if runtime is not None:
        if status == JobStatus.PROCESSING:
            if runtime.stage == "queued":
                runtime.stage = "processing"
            runtime.progress_percent = max(1, min(99, runtime.progress_percent))
        elif status == JobStatus.SUCCEEDED:
            runtime.stage = "completed"
            runtime.progress_percent = 100
        elif status == JobStatus.FAILED and runtime.stage not in {"canceled"}:
            runtime.stage = "failed"
            runtime.progress_percent = min(99, runtime.progress_percent)
            if error_message:
                runtime.detail_message = error_message
        db.add(runtime)
        db.commit()
        db.refresh(runtime)

    return job


def upsert_job_runtime(
    db: Session,
    job_id: str,
    *,
    stage: str | None = None,
    progress_percent: int | None = None,
    detail_message: str | None = None,
    cancel_requested: bool | None = None,
) -> JobRuntime:
    runtime = get_job_runtime(db, job_id)
    if runtime is None:
        runtime = JobRuntime(job_id=job_id, stage="queued", progress_percent=0, cancel_requested=False)

    if stage is not None:
        runtime.stage = stage
    if progress_percent is not None:
        runtime.progress_percent = max(0, min(100, int(progress_percent)))
    if detail_message is not None:
        runtime.detail_message = detail_message
    if cancel_requested is not None:
        runtime.cancel_requested = cancel_requested

    db.add(runtime)
    db.commit()
    db.refresh(runtime)
    return runtime


def request_job_cancel(db: Session, job_id: str) -> JobRuntime:
    runtime = upsert_job_runtime(
        db,
        job_id,
        stage="cancel_requested",
        detail_message="cancel requested by user",
        cancel_requested=True,
    )
    return runtime


def is_cancel_requested(db: Session, job_id: str) -> bool:
    runtime = get_job_runtime(db, job_id)
    return bool(runtime.cancel_requested) if runtime else False


def mark_job_canceled(db: Session, job_id: str, reason: str = "canceled by user") -> None:
    upsert_job_runtime(
        db,
        job_id,
        stage="canceled",
        detail_message=reason,
        cancel_requested=True,
    )
    set_job_status(db, job_id, JobStatus.FAILED, error_message=reason)


def create_project(
    db: Session,
    *,
    name: str,
    transition_duration_seconds: int,
    transition_prompt: str,
    transition_negative_prompt: str | None,
    last_clip_duration_seconds: int,
    last_clip_motion_style: str,
    bgm_path: str | None,
    bgm_volume: float,
    final_output_path: str | None = None,
) -> Project:
    project = Project(
        name=name,
        status=ProjectStatus.DRAFT,
        transition_duration_seconds=transition_duration_seconds,
        transition_prompt=transition_prompt,
        transition_negative_prompt=transition_negative_prompt,
        last_clip_duration_seconds=last_clip_duration_seconds,
        last_clip_motion_style=last_clip_motion_style,
        bgm_path=bgm_path,
        bgm_volume=bgm_volume,
        final_output_path=final_output_path,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def list_projects(db: Session, limit: int = 20) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def set_project_status(db: Session, project_id: str, status: ProjectStatus) -> Project:
    project = get_project(db, project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    project.status = status
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project_by_name(db: Session, name: str) -> Project | None:
    stmt = select(Project).where(Project.name == name).limit(1)
    return db.scalar(stmt)


def create_project_run(db: Session, project_id: str, job_id: str) -> ProjectRun:
    row = ProjectRun(project_id=project_id, job_id=job_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_asset(
    db: Session,
    *,
    project_id: str,
    order_index: int,
    file_name: str,
    file_path: str,
    width: int,
    height: int,
) -> Asset:
    asset = Asset(
        project_id=project_id,
        order_index=order_index,
        file_name=file_name,
        file_path=file_path,
        width=width,
        height=height,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def list_assets_by_project(db: Session, project_id: str) -> list[Asset]:
    stmt = (
        select(Asset)
        .where(Asset.project_id == project_id)
        .order_by(Asset.order_index.asc(), Asset.created_at.asc())
    )
    return list(db.scalars(stmt))


def get_latest_active_project_job(db: Session, project_id: str) -> Job | None:
    stmt = (
        select(ProjectRun)
        .where(ProjectRun.project_id == project_id)
        .order_by(ProjectRun.created_at.desc())
        .limit(20)
    )
    rows = list(db.scalars(stmt))
    for row in rows:
        job = get_job(db, row.job_id)
        if job is None:
            continue
        if job.status in {JobStatus.QUEUED, JobStatus.PROCESSING}:
            return job
    return None
