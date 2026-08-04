from unittest.mock import patch, MagicMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from pyrate_limiter import Limiter, Rate, Duration

from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters


@pytest.fixture
def mock_ai_analyst():
    mock_response = MagicMock()
    mock_response.json.return_value = {"task_id": str(uuid4())}
    mock_response.raise_for_status.return_value = None
    with patch("src.api.experiences.requests.post", return_value=mock_response) as mock_post:
        yield mock_post

@pytest.fixture(autouse=True)
def reset_analysis_limiters():
    for limiters in analysis_rate_limiters.values():
        for limiter in limiters.values():
            limiter.limiter = Limiter(Rate(100, Duration.HOUR))
            for bucket in limiter.limiter.buckets():
                bucket.flush()
    yield
    for limiters in analysis_rate_limiters.values():
        for limiter in limiters.values():
            for bucket in limiter.limiter.buckets():
                bucket.flush()

def test_post_experience_returns_201(authenticated_client: TestClient, mock_ai_analyst):
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 201


def test_post_experience_response_shape(authenticated_client: TestClient, mock_ai_analyst):
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    body = response.json()
    assert "message" in body
    assert "data" in body
    assert "id" in body["data"]


def test_post_experience_id_is_uuid(authenticated_client: TestClient, mock_ai_analyst):
    import uuid
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    body = response.json()
    _ = uuid.UUID(body["data"]["id"])


def test_post_experience_persisted_in_db(authenticated_client: TestClient, session: Session, mock_ai_analyst):
    from src.db.models import Experience
    data = {"type": "career", "content": {"role": "engineer"}}
    response = authenticated_client.post("/experiences", json=data)
    experience_id = response.json()["data"]["id"]
    record = session.get(Experience, experience_id)
    assert record is not None
    assert record.content == {"role": "engineer"}


def test_post_experience_user_id_matches_token(authenticated_client: TestClient, session: Session, mock_ai_analyst):
    from src.db.models import Experience
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    experience_id = response.json()["data"]["id"]
    token = authenticated_client.cookies.get("accessToken")
    assert token is not None
    payload = check_auth(session, token)
    record = session.get(Experience, experience_id)
    assert record is not None
    assert record.user_id == payload.sub


def test_post_experience_no_token_returns_401(client: TestClient, mock_ai_analyst):
    data = {"type": "career", "content": {"a": "b"}}
    response = client.post("/experiences", json=data)
    assert response.status_code == 401


def test_post_experience_missing_type_returns_422(authenticated_client: TestClient, mock_ai_analyst):
    data = {"content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 422


def test_post_experience_missing_content_returns_422(authenticated_client: TestClient, mock_ai_analyst):
    data = {"type": "career"}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 422


def test_post_experience_empty_body_returns_422(authenticated_client: TestClient, mock_ai_analyst):
    response = authenticated_client.post("/experiences", json={})
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_type", ["", 123, None])
def test_post_experience_invalid_type_returns_422(authenticated_client: TestClient, invalid_type, mock_ai_analyst):
    data = {"type": invalid_type, "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 422


def test_post_experience_db_commit_failure_returns_500(authenticated_client: TestClient, mock_ai_analyst):
    with patch.object(Session, "commit") as commit:
        commit.side_effect = Exception("DB down")
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        assert response.status_code == 500

class TestGetExperienceById:
    def test_success(self, authenticated_client: TestClient, mock_ai_analyst):
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        experience_id = response.json()["data"]["id"]
        response = authenticated_client.get(f"/experiences/{experience_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == experience_id
    def test_not_found(self, authenticated_client: TestClient, mock_ai_analyst):
        response = authenticated_client.get(f"/experiences/{uuid4()}")
        assert response.status_code == 404
    # TODO: test_forbidden
    # def test_forbidden(self, authenticated_client: TestClient, session: Session):
    #     data = {"type": "career", "content": {"a": "b"}}
    #     response = authenticated_client.post("/experiences", json=data)
    #     experience_id = response.json()["data"]["id"]
    #     result = session.exec(select(Experience).where(Experience.id == UUID(experience_id))).one()
    #     result.user_id = uuid4()
    #     session.add(result)
    #     session.commit()
    #     response = authenticated_client.get(f"/experiences/{experience_id}")
    #     assert response.status_code == 403

class TestPutExperienceById:
    def test_success(self, authenticated_client: TestClient, mock_ai_analyst):
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        experience_id = response.json()["data"]["id"]
        update_data = {"content": {"role": "engineer"}, "importance": 4}
        response = authenticated_client.put(f"/experiences/{experience_id}", json=update_data)
        response = authenticated_client.get(f"/experiences/{experience_id}")
        assert response.status_code == 200
        assert response.json()["data"]["content"] == {"role": "engineer"}
        assert response.json()["data"]["importance"] == 4
    def test_invalid_importance_returns_400(self, authenticated_client: TestClient, mock_ai_analyst):
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        experience_id = response.json()["data"]["id"]
        update_data = {"content": {"role": "engineer"}, "importance": 6}
        response = authenticated_client.put(f"/experiences/{experience_id}", json=update_data)
        assert response.status_code == 422
    def test_not_found(self, authenticated_client: TestClient, mock_ai_analyst):
        update_data = {"content": {"role": "engineer"}, "importance": 4}
        response = authenticated_client.put(f"/experiences/{uuid4()}", json=update_data)
        assert response.status_code == 404