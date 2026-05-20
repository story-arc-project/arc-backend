from os import getenv
from celery import Celery

celery = Celery(
    "tasks",
    broker=f"amqp://{getenv("RABBITMQ_USER")}:{getenv("RABBITMQ_PASSWORD")}@rabbitmq:5672//",
    include=["src.queue.tasks"],
)

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)