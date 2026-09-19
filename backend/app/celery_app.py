from celery import Celery

from app.core.config import settings
celery_app =Celery(
    "rag_knowledge_base",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.ingestion.tasks"],
)

celery_app.conf.update(
    task_acks_late = False,
    worker_perfetch_multiplier = 1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone ="UTC",
    enable_utc =True
)