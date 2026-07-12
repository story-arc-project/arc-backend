from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from os import getenv

from tests.const import AUTHENTICATED_EMAIL

class TestAuthAccess:
    def test_auth_access_fail(self, authenticated_client: TestClient):
        response = authenticated_client.get("/admin/status")
        assert response.status_code == 404
        assert response.text == '{"detail":"Not Found"}'

    def test_auth_access_success(self, authenticated_client: TestClient, monkeypatch: MonkeyPatch):
        monkeypatch.setenv("ADMIN_EMAILS", AUTHENTICATED_EMAIL)
        assert getenv("ADMIN_EMAILS") == AUTHENTICATED_EMAIL
        response = authenticated_client.get("/admin/status")
        assert response.status_code == 200