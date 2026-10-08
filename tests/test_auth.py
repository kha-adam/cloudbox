from app.database import SessionLocal
from app.config import settings
from app.models import User
from app.main import app

import jwt
from fastapi.testclient import TestClient

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

def test_login():
    client.post(
        "/auth/register",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["access_token"]

def test_login_wrong_password():
    client.post(
        "/auth/register",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "adam@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

def test_login_wrong_password():
    client.post(
        "/auth/register",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "adam@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

def test_login_token_contains_user_id():
    register_response = client.post(
        "/auth/register",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    user_id = register_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={
            "email": "adam@example.com",
            "password": "supersecret123",
        },
    )

    token = login_response.json()["access_token"]

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == str(user_id)
    assert "exp" in payload

