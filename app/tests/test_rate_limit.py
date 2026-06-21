from datetime import date
from typing import Annotated
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Cookie
from fastapi.testclient import TestClient
from pyrate_limiter import Duration, Limiter, Rate
from sqlmodel import Session

from src.db.db import SessionDep
from src.db.models import Experience, UserProfile
from src.enums import Affiliation, ErrorResponseCode
from src.main import app
from src.utils.auth import check_auth
from src.utils.ratelimit import analysis_rate_limiters


class TestAnalysisRateLimit:
    @pytest.fixture(autouse=True)
    def reset_analysis_limiters(self):
        for limiters in analysis_rate_limiters.values():
            for limiter in limiters.values():
                limiter.limiter = Limiter(Rate(1, Duration.HOUR))
                for bucket in limiter.limiter.buckets():
                    bucket.flush()
        yield
        for limiters in analysis_rate_limiters.values():
            for limiter in limiters.values():
                for bucket in limiter.limiter.buckets():
                    bucket.flush()

    @pytest.fixture
    def mock_ai_analyst(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": str(uuid4())}
        mock_response.raise_for_status.return_value = None
        with patch("src.api.analysis.requests.post", return_value=mock_response) as mock_post:
            yield mock_post

    @pytest.fixture
    def mock_experience_ai_analyst(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": str(uuid4())}
        mock_response.raise_for_status.return_value = None
        with patch("src.api.experiences.requests.post", return_value=mock_response) as mock_post:
            yield mock_post

    def _add_profile(self, session: Session, user_id):
        profile = UserProfile(
            user_id=user_id,
            name="Test User",
            birth=date(2000, 1, 1),
            affiliation=Affiliation.STUDENT,
            school="Test University",
            department="Computer Science",
            phone="01012345678",
            worry=["career"],
            interest=["backend"],
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile

    def _add_experience(self, session: Session, user_id):
        experience = Experience(
            user_id=user_id,
            type="career",
            importance=3,
            content={"title": "Internship", "description": "Built an API"},
        )
        session.add(experience)
        session.commit()
        session.refresh(experience)
        return experience

    def _authenticated_user_id(self, authenticated_client: TestClient, session: Session):
        payload = check_auth(session, authenticated_client.cookies.get("accessToken"))
        return payload.sub

    def _set_analysis_limit(self, analysis_type: str, scope: str, limit: int):
        limiter = analysis_rate_limiters[analysis_type][scope]
        limiter.limiter = Limiter(Rate(limit, Duration.HOUR))
        for bucket in limiter.limiter.buckets():
            bucket.flush()

    def test_keyword_analysis_is_rate_limited_by_user(
        self,
        authenticated_client: TestClient,
        mock_ai_analyst,
    ):
        self._set_analysis_limit("keyword", "user", 1)
        self._set_analysis_limit("keyword", "ip", 10)

        first_response = authenticated_client.post(
            "/analysis/keyword",
            json={"keywords": ["api"]},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        second_response = authenticated_client.post(
            "/analysis/keyword",
            json={"keywords": ["api"]},
            headers={"X-Forwarded-For": "203.0.113.11"},
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert second_response.json()["code"] == ErrorResponseCode.TOO_MANY_ATTEMPTS
        assert mock_ai_analyst.call_count == 1

    def test_keyword_analysis_is_rate_limited_by_ip(
        self,
        authenticated_client: TestClient,
        mock_ai_analyst,
    ):
        self._set_analysis_limit("keyword", "user", 10)
        self._set_analysis_limit("keyword", "ip", 1)

        first_response = authenticated_client.post(
            "/analysis/keyword",
            json={"keywords": ["api"]},
            headers={"X-Forwarded-For": "203.0.113.20"},
        )
        second_response = authenticated_client.post(
            "/analysis/keyword",
            json={"keywords": ["api"]},
            headers={"X-Forwarded-For": "203.0.113.20"},
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert second_response.json()["code"] == ErrorResponseCode.TOO_MANY_ATTEMPTS
        assert mock_ai_analyst.call_count == 1

    def test_comprehensive_analysis_is_rate_limited_by_user(
        self,
        authenticated_client: TestClient,
        session: Session,
        mock_ai_analyst,
    ):
        self._set_analysis_limit("comprehensive", "user", 1)
        self._set_analysis_limit("comprehensive", "ip", 10)
        user_id = self._authenticated_user_id(authenticated_client, session)
        self._add_profile(session, user_id)
        experience = self._add_experience(session, user_id)

        request_body = {"experiences": [str(experience.id)]}
        first_response = authenticated_client.post(
            "/analysis/comprehensive",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.30"},
        )
        second_response = authenticated_client.post(
            "/analysis/comprehensive",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.31"},
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert second_response.json()["code"] == ErrorResponseCode.TOO_MANY_ATTEMPTS
        assert mock_ai_analyst.call_count == 1

    def test_post_experience_is_rate_limited_by_user(
        self,
        authenticated_client: TestClient,
        mock_experience_ai_analyst,
    ):
        self._set_analysis_limit("individual", "user", 1)
        self._set_analysis_limit("individual", "ip", 10)

        request_body = {"type": "career", "content": {"title": "Internship"}}
        first_response = authenticated_client.post(
            "/experiences",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.40"},
        )
        second_response = authenticated_client.post(
            "/experiences",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.41"},
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 429
        assert second_response.json()["code"] == ErrorResponseCode.TOO_MANY_ATTEMPTS
        assert mock_experience_ai_analyst.call_count == 1

    def test_post_experience_is_rate_limited_by_ip(
        self,
        authenticated_client: TestClient,
        mock_experience_ai_analyst,
    ):
        self._set_analysis_limit("individual", "user", 10)
        self._set_analysis_limit("individual", "ip", 1)

        request_body = {"type": "career", "content": {"title": "Internship"}}
        first_response = authenticated_client.post(
            "/experiences",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.50"},
        )
        second_response = authenticated_client.post(
            "/experiences",
            json=request_body,
            headers={"X-Forwarded-For": "203.0.113.50"},
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 429
        assert second_response.json()["code"] == ErrorResponseCode.TOO_MANY_ATTEMPTS
        assert mock_experience_ai_analyst.call_count == 1

    def test_check_auth_runs_once_per_rate_limited_request(
        self,
        authenticated_client: TestClient,
        mock_ai_analyst,
    ):
        auth_call_count = 0

        def counting_check_auth(
            session: SessionDep,
            accessToken: Annotated[str | None, Cookie()] = None,
        ):
            nonlocal auth_call_count
            auth_call_count += 1
            return check_auth(session, accessToken)

        app.dependency_overrides[check_auth] = counting_check_auth
        try:
            response = authenticated_client.post(
                "/analysis/keyword",
                json={"keywords": ["api"]},
            )
        finally:
            app.dependency_overrides.pop(check_auth, None)

        assert response.status_code == 200
        assert auth_call_count == 1
