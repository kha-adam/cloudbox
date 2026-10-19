from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.security import create_access_token, decode_access_token


def test_decode_access_token_returns_user_id():
    token = create_access_token(123)

    assert decode_access_token(token) == 123


def test_decode_access_token_rejects_expired_token():
    token = jwt.encode(
        {
            "sub": "123",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_missing_subject():
    token = jwt.encode(
        {
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_decode_access_token_rejects_missing_expiration():
    token = jwt.encode(
        {"sub": "123"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_decode_access_token_rejects_non_numeric_subject():
    token = jwt.encode(
        {
            "sub": "abc",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ValueError, match="Invalid token subject"):
        decode_access_token(token)


@pytest.mark.parametrize("subject", ["0", "-1", "1.5", ""])
def test_decode_access_token_rejects_invalid_user_ids(subject):
    token = jwt.encode(
        {
            "sub": subject,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ValueError, match="Invalid token subject"):
        decode_access_token(token)
