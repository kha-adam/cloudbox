from app.database import SessionLocal
from app.models import User

from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_register_user():
    response = client.post(
        "auth/register",
        json={
            "email" : "user@example.com",
            "password" : "supersecret123",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "user@example.com"
    assert isinstance(data["id"], int)
    assert "password" not in data
    assert 'password_hash' not in data

def test_register_hashes_password():
    response = client.post(
        "/auth/register",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    assert response.status_code == 201

    db = SessionLocal()

    try:
        user = db.query(User).filter(
            User.email == "adam@example.com"
        ).one()

        assert user.password_hash != "supersecret123"
        assert user.password_hash.startswith("$argon2")
    finally:
        db.close()

def test_register_duplicate_email():
    payload = {
        "email": "adam@example.com",
        "password": "supersecret123",
    }

    first_response = client.post(
        "/auth/register",
        json=payload,
    )

    second_response = client.post(
        "/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email already registered"

def test_register_normalizes_email():
    response = client.post(
        "/auth/register",
        json={
            "email": "  Adam@Example.COM  ",
            "password": "supersecret123",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "adam@example.com"
