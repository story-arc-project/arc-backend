from fastapi.testclient import TestClient

def test_cors_preflight(client: TestClient):
    response = client.options(
        "/auth/login",
        headers={
            "Access-Control-Request-Method": "POST"
        }
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == client.headers["Origin"]
    assert "access-control-allow-methods" in response.headers

def test_cors_allowed_origin(client: TestClient):
    response = client.post("/auth/signup", json={
        "email": "test@gmail.com",
        "password": "testpassword"
    })
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == client.headers["Origin"]

def test_cors_disallowed_origin(client: TestClient):
    response = client.post("/auth/signup", json={
        "email": "test@gmail.com",
        "password": "testpassword"
    }, headers={
        "Origin": "https://badhost.test"
    })
    assert response.status_code == 201
    assert "access-control-allow-origin" not in response.headers