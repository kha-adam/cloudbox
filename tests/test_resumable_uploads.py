from pathlib import Path
from fastapi.testclient import TestClient
import hashlib

from app.database import SessionLocal
from app.main import app
from app.models import File, User, UploadSession
from app.config import settings
from app.database import SessionLocal
from app.models import UploadSession

from tests.conftest import TEST_STORAGE_DIR
from tests.helpers import get_auth_headers, client

def test_create_upload_session():
    headers = get_auth_headers()
    total_size = 12 * 1024 * 1024  # 12 MiB

    response = client.post(
        "/uploads",
        json={
            "filename": "archive.zip",
            "total_size": total_size,
            "mime_type": "application/zip",
        },
        headers=headers,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["chunk_size"] == 5 * 1024 * 1024
    assert data["total_chunks"] == 3
    assert data["status"] == "in_progress"
    assert data["upload_id"]
    assert data["expires_at"]

    db = SessionLocal()

    try:
        session = db.get(UploadSession, data["upload_id"])

        assert session is not None
        assert session.filename == "archive.zip"
        assert session.total_size == total_size
        assert session.total_chunks == 3
        assert session.status == "in_progress"

        user = db.get(User, session.owner_id)

        assert user is not None
        assert user.reserved_storage == total_size
        assert user.storage_used == 0

    finally:
        db.close()

    upload_path = TEST_STORAGE_DIR / "uploads" / data["upload_id"]
    assert not upload_path.exists()

def test_create_upload_session_exceeds_quota():
    headers = get_auth_headers()
    quota = settings.max_storage_per_user
    max_upload = settings.max_upload_size

    full_sessions, remainder = divmod(quota, max_upload)

    for _ in range(full_sessions):
        response = client.post(
            "/uploads",
            json={
                "filename": "reserved.bin",
                "total_size": max_upload,
                "mime_type": "application/octet-stream",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()

    if remainder:
        response = client.post(
            "/uploads",
            json={
                "filename": "reserved-remainder.bin",
                "total_size": remainder,
                "mime_type": "application/octet-stream",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()

    response = client.post(
        "/uploads",
        json={
            "filename": "over-quota.bin",
            "total_size": 1,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )

    assert response.status_code == 413, response.json()
    assert response.json()["detail"] == "User storage quota exceeded"

def test_create_upload_session_exceeds_max_upload_size():
    headers = get_auth_headers()

    response = client.post(
        "/uploads",
        json={
            "filename": "too-large.bin",
            "total_size": settings.max_upload_size + 1,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )

    assert response.status_code == 422, response.json()

def test_create_upload_session_rejects_zero_size():
    response = client.post(
        "/uploads",
        json={
            "filename": "empty.bin",
            "total_size": 0,
            "mime_type": "application/octet-stream",
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 422

def test_create_upload_session_exceeds_max_upload_size():
    response = client.post(
        "/uploads",
        json={
            "filename": "too-large.bin",
            "total_size": settings.max_upload_size + 1,
            "mime_type": "application/octet-stream",
        },
        headers=get_auth_headers(),
    )
    print(response.status_code)
    print(response.json())
    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds maximum allowed size"

def test_create_upload_session_requires_authentication():
    response = client.post(
        "/uploads",
        json={
            "filename": "private.bin",
            "total_size": 1024,
            "mime_type": "application/octet-stream",
        },
    )

    assert response.status_code in (401, 403)

def test_upload_valid_chunk():
    headers = get_auth_headers()
    content = b"A" * (5 * 1024 * 1024)

    # Create an upload session that expects one full chunk.
    session_response = client.post(
        "/uploads",
        json={
            "filename": "chunk-test.bin",
            "total_size": len(content),
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )

    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    # Upload chunk zero.
    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        content=content,
        headers=headers,
    )

    assert response.status_code == 200, response.json()

    data = response.json()
    assert data["upload_id"] == upload_id
    assert data["chunk_index"] == 0
    assert data["size"] == len(content)
    assert data["sha256"] == hashlib.sha256(content).hexdigest()
    assert data["status"] == "received"

    # Verify the chunk was actually persisted.
    chunk_path = (
        TEST_STORAGE_DIR
        / "uploads"
        / upload_id
        / "0.chunk"
    )
    assert chunk_path.is_file()
    assert chunk_path.stat().st_size == len(content)
    assert chunk_path.read_bytes() == content

def test_upload_chunk_rejects_incomplete_chunk():
    headers = get_auth_headers()
    expected_size = 1024
    content = b"A" * (expected_size - 1)

    session_response = client.post(
        "/uploads",
        json={
            "filename": "incomplete.bin",
            "total_size": expected_size,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        content=content,
        headers=headers,
    )

    assert response.status_code == 400, response.json()

    chunk_path = TEST_STORAGE_DIR / "uploads" / upload_id / "0.chunk"
    assert not chunk_path.exists()

def test_upload_chunk_rejects_oversized_chunk():
    headers = get_auth_headers()
    expected_size = 1024
    content = b"A" * (expected_size + 1)

    session_response = client.post(
        "/uploads",
        json={
            "filename": "oversized.bin",
            "total_size": expected_size,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        content=content,
        headers=headers,
    )

    assert response.status_code == 400, response.json()

    chunk_path = TEST_STORAGE_DIR / "uploads" / upload_id / "0.chunk"
    assert not chunk_path.exists()

def test_upload_same_chunk_twice_is_idempotent():
    headers = get_auth_headers()
    content = b"A" * 1024

    session_response = client.post(
        "/uploads",
        json={
            "filename": "retry.bin",
            "total_size": len(content),
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    url = f"/uploads/{upload_id}/chunks/0"

    first_response = client.put(url, content=content, headers=headers)
    assert first_response.status_code == 200, first_response.json()

    second_response = client.put(url, content=content, headers=headers)
    assert second_response.status_code == 200, second_response.json()

    chunk_path = TEST_STORAGE_DIR / "uploads" / upload_id / "0.chunk"
    assert chunk_path.read_bytes() == content
    assert chunk_path.stat().st_size == len(content)

def test_upload_conflicting_chunk_retry_is_rejected():
    headers = get_auth_headers()
    original_content = b"A" * 1024
    conflicting_content = b"B" * 1024

    session_response = client.post(
        "/uploads",
        json={
            "filename": "conflict.bin",
            "total_size": len(original_content),
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    url = f"/uploads/{upload_id}/chunks/0"

    first_response = client.put(
        url, content=original_content, headers=headers
    )
    assert first_response.status_code == 200, first_response.json()

    retry_response = client.put(
        url, content=conflicting_content, headers=headers
    )

    assert retry_response.status_code == 409, retry_response.json()

    chunk_path = TEST_STORAGE_DIR / "uploads" / upload_id / "0.chunk"
    assert chunk_path.read_bytes() == original_content

def test_upload_status_reports_all_chunks_missing():
    headers = get_auth_headers()
    total_size = 12 * 1024 * 1024

    session_response = client.post(
        "/uploads",
        json={
            "filename": "resume.bin",
            "total_size": total_size,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    response = client.get(f"/uploads/{upload_id}", headers=headers)

    assert response.status_code == 200, response.json()
    data = response.json()

    assert data["upload_id"] == upload_id
    assert data["total_size"] == total_size
    assert data["chunk_size"] == 5 * 1024 * 1024
    assert data["total_chunks"] == 3
    assert data["received_chunks"] == []
    assert data["missing_chunks"] == [0, 1, 2]
    assert data["status"] == "in_progress"

def test_upload_status_updates_after_receiving_chunk():
    headers = get_auth_headers()
    chunk_size = 5 * 1024 * 1024
    total_size = 12 * 1024 * 1024

    session_response = client.post(
        "/uploads",
        json={
            "filename": "partial.bin",
            "total_size": total_size,
            "mime_type": "application/octet-stream",
        },
        headers=headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    chunk_content = b"A" * chunk_size
    chunk_response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        content=chunk_content,
        headers=headers,
    )
    assert chunk_response.status_code == 200, chunk_response.json()

    response = client.get(f"/uploads/{upload_id}", headers=headers)

    assert response.status_code == 200, response.json()
    data = response.json()

    assert data["received_chunks"] == [0]
    assert data["missing_chunks"] == [1, 2]
    assert data["status"] == "in_progress"

def test_upload_status_cannot_be_accessed_by_another_user():
    owner_headers = get_auth_headers("owner@example.com")
    other_headers = get_auth_headers("other@example.com")

    session_response = client.post(
        "/uploads",
        json={
            "filename": "private.bin",
            "total_size": 1024,
            "mime_type": "application/octet-stream",
        },
        headers=owner_headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    response = client.get(
        f"/uploads/{upload_id}",
        headers=other_headers,
    )

    assert response.status_code == 404, response.json()

def test_upload_chunk_cannot_be_uploaded_by_another_user():
    owner_headers = get_auth_headers("chunk-owner@example.com")
    other_headers = get_auth_headers("chunk-other@example.com")

    content = b"A" * 1024

    session_response = client.post(
        "/uploads",
        json={
            "filename": "private.bin",
            "total_size": len(content),
            "mime_type": "application/octet-stream",
        },
        headers=owner_headers,
    )
    assert session_response.status_code == 201, session_response.json()
    upload_id = session_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        content=content,
        headers=other_headers,
    )

    assert response.status_code == 404, response.json()

    chunk_path = TEST_STORAGE_DIR / "uploads" / upload_id / "0.chunk"
    assert not chunk_path.exists()

