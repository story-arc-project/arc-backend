import pytest
from fastapi.testclient import TestClient

CAMPAIGN = "analysis-satisfaction"

# ------------------------------------------------------------------
# GET /status
# ------------------------------------------------------------------

def test_status_initial(authenticated_client: TestClient):
    response = authenticated_client.get(
        f"/feedback/campaigns/{CAMPAIGN}/status"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "success"
    assert body["data"] == {
        "has_seen": False,
        "has_responded": False,
    }


# ------------------------------------------------------------------
# POST /prompt-shown
# ------------------------------------------------------------------

def test_prompt_shown_first_time(authenticated_client: TestClient):
    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["created"] is True


def test_prompt_shown_second_time_returns_created_false(
    authenticated_client: TestClient,
):
    authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["created"] is False


# ------------------------------------------------------------------
# prompt-shown updates status
# ------------------------------------------------------------------

def test_status_after_prompt(authenticated_client: TestClient):
    authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    response = authenticated_client.get(
        f"/feedback/campaigns/{CAMPAIGN}/status"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "has_seen": True,
        "has_responded": False,
    }


# ------------------------------------------------------------------
# POST /responses
# ------------------------------------------------------------------

def test_submit_response(authenticated_client: TestClient):
    authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": 5,
            "comment": "Great experience",
            "context": {
                "analysis_id": "123",
                "analysis_type": "keyword",
            },
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["responded_at"] is not None


def test_status_after_response(authenticated_client: TestClient):
    authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/prompt-shown",
        json={
            "trigger_source": "analysis_completed"
        },
    )

    authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": 5,
            "comment": "Good",
            "context": {},
        },
    )

    response = authenticated_client.get(
        f"/feedback/campaigns/{CAMPAIGN}/status"
    )

    assert response.status_code == 200

    assert response.json()["data"] == {
        "has_seen": True,
        "has_responded": True,
    }


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

@pytest.mark.parametrize("rating", [0, 6])
def test_rating_validation(
    authenticated_client: TestClient,
    rating: int,
):
    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": rating,
            "comment": None,
            "context": None,
        },
    )

    assert response.status_code == 422


def test_comment_500_characters_ok(authenticated_client: TestClient):
    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": 5,
            "comment": "a" * 500,
            "context": None,
        },
    )

    assert response.status_code == 200


def test_comment_501_characters_rejected(authenticated_client: TestClient):
    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": 5,
            "comment": "a" * 501,
            "context": None,
        },
    )

    assert response.status_code == 422


# ------------------------------------------------------------------
# Campaign validation
# ------------------------------------------------------------------

def test_invalid_campaign(authenticated_client: TestClient):
    response = authenticated_client.get(
        "/feedback/campaigns/not-a-campaign/status"
    )

    assert response.status_code == 400


# ------------------------------------------------------------------
# Upsert behavior
# ------------------------------------------------------------------

def test_response_without_prompt_shown(authenticated_client: TestClient):
    response = authenticated_client.post(
        f"/feedback/campaigns/{CAMPAIGN}/responses",
        json={
            "rating": 4,
            "comment": "Hello",
            "context": {},
        },
    )

    assert response.status_code == 200

    status = authenticated_client.get(
        f"/feedback/campaigns/{CAMPAIGN}/status"
    )

    assert status.status_code == 200

    assert status.json()["data"] == {
        "has_seen": True,
        "has_responded": True,
    }