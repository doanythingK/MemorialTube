from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Job, JobStatus, Project, ProjectStatus


def create_job(db: Session, job_type: str) -> Job:
    job = Job(job_type=job_type, status=JobStatus.QUEUED)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


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
    return job


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
