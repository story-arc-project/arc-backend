from unittest.mock import patch
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.db.models import Experience
from src.utils.auth import check_auth


def test_post_experience_returns_201(authenticated_client: TestClient):
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 201


def test_post_experience_response_shape(authenticated_client: TestClient):
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    body = response.json()
    assert "message" in body
    assert "data" in body
    assert "id" in body["data"]


def test_post_experience_id_is_uuid(authenticated_client: TestClient):
    import uuid
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    body = response.json()
    _ = uuid.UUID(body["data"]["id"])


def test_post_experience_persisted_in_db(authenticated_client: TestClient, session: Session):
    from src.db.models import Experience
    data = {"type": "career", "content": {"role": "engineer"}}
    response = authenticated_client.post("/experiences", json=data)
    experience_id = response.json()["data"]["id"]
    record = session.get(Experience, experience_id)
    assert record is not None
    assert record.content == {"role": "engineer"}


def test_post_experience_user_id_matches_token(authenticated_client: TestClient, session: Session):
    from src.db.models import Experience
    data = {"type": "career", "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    experience_id = response.json()["data"]["id"]
    record = session.get(Experience, experience_id)
    token = authenticated_client.cookies.get("accessToken")
    assert token is not None
    payload = check_auth(session, token)
    assert record.user_id == payload.sub


def test_post_experience_no_token_returns_401(client: TestClient):
    data = {"type": "career", "content": {"a": "b"}}
    response = client.post("/experiences", json=data)
    assert response.status_code == 401


def test_post_experience_missing_type_returns_400(authenticated_client: TestClient):
    data = {"content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 400


def test_post_experience_missing_content_returns_400(authenticated_client: TestClient):
    data = {"type": "career"}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 400


def test_post_experience_empty_body_returns_400(authenticated_client: TestClient):
    response = authenticated_client.post("/experiences", json={})
    assert response.status_code == 400


@pytest.mark.parametrize("invalid_type", ["", 123, None])
def test_post_experience_invalid_type_returns_400(authenticated_client: TestClient, invalid_type):
    data = {"type": invalid_type, "content": {"a": "b"}}
    response = authenticated_client.post("/experiences", json=data)
    assert response.status_code == 400


def test_post_experience_db_commit_failure_returns_500(authenticated_client: TestClient):
    with patch.object(Session, "commit") as commit:
        commit.side_effect = Exception("DB down")
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        assert response.status_code == 500

class TestGetExperienceById:
    def test_success(self, authenticated_client: TestClient):
        data = {"type": "career", "content": {"a": "b"}}
        response = authenticated_client.post("/experiences", json=data)
        experience_id = response.json()["data"]["id"]
        response = authenticated_client.get(f"/experiences/{experience_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == experience_id
    def test_not_found(self, authenticated_client: TestClient):
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