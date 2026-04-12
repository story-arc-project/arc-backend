import os
from fastapi.testclient import TestClient
import pytest
from uuid import uuid4
from unittest.mock import patch
from testcontainers.rabbitmq import RabbitMqContainer

from src.main import app


@pytest.fixture(scope="session")
def rabbitmq():
    with RabbitMqContainer("rabbitmq:4.2.5-management-alpine") as container:
        os.environ["RABBITMQ_USER"] = container.username
        os.environ["RABBITMQ_PASSWORD"] = container.password
        os.environ["INTERNAL_SECRET"] = "test-secret"
        os.environ["INTERNAL_ROUTE"] = "internal"

        # point celery to the testcontainer
        broker_url = f"amqp://{container.username}:{container.password}@{container.get_container_host_ip()}:{container.get_exposed_port(5672)}//"

        # patch celery broker before importing tasks
        os.environ["RABBITMQ_BROKER_URL"] = broker_url
        yield container


@pytest.fixture(scope="session")
def celery_app(rabbitmq):
    broker_url = os.environ["RABBITMQ_BROKER_URL"]

    from src.queue.celery_app import celery
    celery.conf.update(
        broker_url=broker_url,
        task_always_eager=True
    )
    return celery


@pytest.fixture
def client(celery_app):
    yield TestClient(app)

def test_task_individual_enqueue(client: TestClient):
    with patch("src.queue.tasks.individual") as mock_individual, \
         patch("src.queue.tasks.call_frontend") as mock_call:

        analysis_id = str(uuid4())
        data = {"summary": "test result"}
        mock_individual.return_value = data

        response = client.post("/individual", json={
            "analysis_id": analysis_id,
            "input": ["test data"]
        })
        
        assert response.status_code == 200
        task_id = response.json()["task_id"]
        assert task_id is not None
        assert isinstance(task_id, str)
        args, kwargs = mock_call.call_args
        endpoint, call_data = args
        assert endpoint == "/internal/individual/complete"
        assert call_data["analysis_id"] == analysis_id
        assert call_data["result"] == data