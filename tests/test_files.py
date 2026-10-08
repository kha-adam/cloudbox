from pathlib import Path
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import File
from app.config import settings

client = TestClient(app)

TEST_STORAGE_DIR = Path(settings.storage_dir)
def get_auth_headers(email = "test@example.com"):
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

def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
    }

def test_upload_file():
    headers = get_auth_headers()
    content = b"Hello CloudBox!"

    response = client.post(
        "/files",
        files={
            "file":(
                "hello.txt",
                content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["filename"] == "hello.txt"
    assert data["size"] == len(content)
    assert len(data["sha256"]) == 64

    db = SessionLocal()

    try:
        file = db.get(File, data["id"])

        assert file is not None
        assert file.filename == "hello.txt"
        assert file.size == len(content)
        assert file.sha256 == data["sha256"]

        storage_path = Path(file.storage_path)

        assert storage_path.is_file()
        assert storage_path.read_bytes() == content

    finally:
        db.close()

def test_upload_and_download_file():
    headers = get_auth_headers()
    content = b"Hello CloudBox!"
    
    upload_response = client.post(
        "/files",
        files={
            "file":(
                "hello.txt",
                content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    download_response = client.get(
        f"files/{file_id}/download", headers=headers,
    )

    assert download_response.status_code == 200
    assert download_response.content == content
    assert "hello.txt" in download_response.headers["content-disposition"]

def test_list_files():
    headers = get_auth_headers()
    first_content = b"First file"
    second_content = b"Second file"

    first_response = client.post(
        "/files",
        files={
            "file": (
                "first.txt",
                first_content,
                "text/plain",
            )
        },
        headers=headers,
    )

    second_response = client.post(
        "/files",
        files={
            "file": (
                "second.txt",
                second_content,
                "text/plain",
            )
        },
        headers=headers,
    )
    assert first_response.status_code == 200
    assert second_response.status_code == 200

    response = client.get("/files", headers=headers,)

    assert response.status_code == 200

    files = response.json()

    assert len(files["items"]) == 2
    assert files["total"] == 2
    assert files["limit"] == 50
    assert files["offset"] == 0

    filenames = {file["filename"] for file in files["items"]}

    assert filenames == {"first.txt", "second.txt"}

def test_delete_file():
    headers = get_auth_headers()
    content = b"File to delete"

    upload_response = client.post(
        "/files",
        files={
            "file": (
                "delete-me.txt",
                content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    db = SessionLocal()

    try:
        file = db.get(File, file_id)

        assert file is not None

        storage_path = Path(file.storage_path)

        assert storage_path.is_file()

    finally:
        db.close()

    delete_response = client.delete(
        f"/files/{file_id}", headers=headers,
    )

    assert delete_response.status_code == 200
    assert delete_response.json() == {
        "message": "File deleted",
        "id": file_id,
    }

    db = SessionLocal()

    try:
        assert db.get(File, file_id) is None
    finally:
        db.close()

    assert not storage_path.exists()

    download_response = client.get(
        f"/files/{file_id}/download", headers=headers,
    )

    assert download_response.status_code == 404

def test_download_nonexistant_file():
    headers = get_auth_headers()
    response = client.get(
        f"/files/99999/download",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "File not found",
    }

def test_delete_nonexistant_file():
    headers = get_auth_headers()
    response = client.delete(
            f"/files/99999",
            headers=headers,
        )
    
    assert response.status_code == 404
    assert response.json() == {
        "detail": "File not found",
    }

def test_download_when_storage_file_is_missing():
    headers = get_auth_headers()
    content = b"Temporary file"

    upload_response = client.post(
        "/files",
        files={
            "file": (
                "missing.txt",
                content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    db = SessionLocal()

    try:
        file = db.get(File, file_id)

        assert file is not None

        storage_path = Path(file.storage_path)
        assert storage_path.is_file()

        storage_path.unlink()

    finally:
        db.close()   

    response = client.get(f"files/{file_id}/download",headers=headers,) 

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Stored file not found",
    }

def test_upload_empty_file():
    headers = get_auth_headers()
    content = b""
    response = client.post(
        "/files",
        files={
            "file": (
                "empty.txt",
                content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["filename"] == "empty.txt"
    assert data["size"] == 0
    assert len(data["sha256"]) == 64

def test_upload_exceeding_file_limit_rejection():
    headers = get_auth_headers()
    oversized_content = b"x" * (settings.max_upload_size + 1)

    response = client.post(
        "/files",
        files={
            "file": (
                "too-large.txt",
                oversized_content,
                "text/plain",
            )
        },
        headers=headers,
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "File exceeds maximum allowed size"
    }
    db = SessionLocal()

    try:
        files = db.query(File).all()
        assert files == []

    finally:
        db.close()

    stored_files = [
        path for path in TEST_STORAGE_DIR.iterdir()
        if path.name != ".gitkeep"
    ]   
    assert stored_files == []

def test_upload_doesnt_use_client_filename_as_storage_path():
    headers = get_auth_headers()
    response = client.post(
        "/files",
        files={
            "file": (
                "../../outside.txt",
                b"secret data",
                "text/plain",
            )
        },
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["filename"] == "../../outside.txt"
    stored_files = [
        path
        for path in TEST_STORAGE_DIR.iterdir()
        if path.name != ".gitkeep"
    ]

    assert len(stored_files) == 1
    assert stored_files[0].name != "../../outside.txt"
    assert stored_files[0].parent == TEST_STORAGE_DIR    

def test_list_files_limit():
    headers = get_auth_headers()
    client.post(
        "/files",
        files={"file": ("first.txt", b"first file", "text/plain")},
        headers=headers,
    )
    client.post(
        "/files",
        files={"file": ("second.txt", b"second file", "text/plain")},
        headers=headers,
    )

    response = client.get("/files?limit=1", headers=headers,)

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 2

def test_list_files_offset():
    headers = get_auth_headers()
    client.post(
        "/files",
        files={"file": ("first.txt", b"first file", "text/plain")},
        headers=headers,
    )
    client.post(
        "/files",
        files={"file": ("second.txt", b"second file", "text/plain")},
        headers=headers,
    )

    response = client.get("/files?limit=1&offset=1", headers=headers,)

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["offset"] == 1
    assert data["total"] == 2

def test_users_only_see_their_own_files():
    alice_headers = get_auth_headers(email="alice@example.com",)

    bob_headers = get_auth_headers(email="bob@example.com")

    alice_upload = client.post(
        "/files",
        files={
            "file": (
                "alice.txt",
                b"alice file",
                "text/plain",
            )
        },
        headers=alice_headers,
    )

    bob_upload = client.post(
        "/files",
        files={
            "file": (
                "bob.txt",
                b"bob file",
                "text/plain",
            )
        },
        headers=bob_headers,
    )

    assert alice_upload.status_code == 200
    assert bob_upload.status_code == 200

    alice_files = client.get(
        "/files",
        headers=alice_headers,
    )

    bob_files = client.get(
        "/files",
        headers=bob_headers,
    )

    assert alice_files.status_code == 200
    assert bob_files.status_code == 200

    alice_names = [
        file["filename"]
        for file in alice_files.json()["items"]
    ]

    bob_names = [
        file["filename"]
        for file in bob_files.json()["items"]
    ]

    assert alice_names == ["alice.txt"]
    assert bob_names == ["bob.txt"]

def test_user_cannot_download_another_users_file():
    alice_headers = get_auth_headers(email="alice@example.com")

    bob_headers = get_auth_headers(email="bob@example.com")

    upload_response = client.post(
        "/files",
        files={
            "file": (
                "secret.txt",
                b"alice secret",
                "text/plain",
            )
        },
        headers=alice_headers,
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    response = client.get(
        f"/files/{file_id}/download",
        headers=bob_headers,
    )

    assert response.status_code == 404

def test_user_cannot_delete_another_users_file():
    alice_headers = get_auth_headers(email="alice@example.com")

    bob_headers = get_auth_headers(email="bob@example.com",)

    upload_response = client.post(
        "/files",
        files={
            "file": (
                "important.txt",
                b"do not delete",
                "text/plain",
            )
        },
        headers=alice_headers,
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    delete_response = client.delete(
        f"/files/{file_id}",
        headers=bob_headers,
    )

    assert delete_response.status_code == 404

    # Alice should still be able to access it.
    download_response = client.get(
        f"/files/{file_id}/download",
        headers=alice_headers,
    )

    assert download_response.status_code == 200
    assert download_response.content == b"do not delete"
