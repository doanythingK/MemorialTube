from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, JobStatus


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
