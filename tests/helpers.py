from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def get_auth_headers(email="test@example.com"):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
        },
    )

    assert response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    return {
        "Authorization": f"Bearer {token}",
    }
