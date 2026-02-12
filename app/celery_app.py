from celery import Celery

from app.config import settings


celery_app = Celery(
    "memorialtube",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)
