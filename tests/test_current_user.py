from app.security import create_access_token
from app.services.users import create_user
from app.security import hash_password
from app.main import app

from fastapi.testclient import TestClient

client = TestClient(app)

def test_current_user_with_valid_token():
    response = client.post(
        "/auth/register",
        json={
            "email": "me@example.com",
            "password": "password123",
        },
    )

    user_id = response.json()["id"]

    token = create_access_token(user_id)

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "email": "me@example.com",
    }


def test_current_user_without_token():
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_current_user_with_invalid_token():
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer definitely-not-a-real-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_current_user_with_tampered_token():
    response = client.post(
        "/auth/register",
        json={
            "email": "tampered@example.com",
            "password": "password123",
        },
    )

    user_id = response.json()["id"]

    token = create_access_token(user_id)
    tampered_token = token[:-1] + ("x" if token[-1] != "x" else "y")

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {tampered_token}",
        },
    )

    assert response.status_code == 401