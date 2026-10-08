from pathlib import Path
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import File
from app.config import settings

client = TestClient(app)

TEST_STORAGE_DIR = Path(settings.storage_dir)

def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
    }

def test_upload_file():

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
    )

    assert upload_response.status_code == 200

    file_id = upload_response.json()["id"]

    download_response = client.get(
        f"files/{file_id}/download"
    )

    assert download_response.status_code == 200
    assert download_response.content == content
    assert "hello.txt" in download_response.headers["content-disposition"]

def test_list_files():
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
    )
    assert first_response.status_code == 200
    assert second_response.status_code == 200

    response = client.get("/files")

    assert response.status_code == 200

    files = response.json()

    assert len(files["items"]) == 2
    assert files["total"] == 2
    assert files["limit"] == 50
    assert files["offset"] == 0

    filenames = {file["filename"] for file in files["items"]}

    assert filenames == {"first.txt", "second.txt"}

def test_delete_file():
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
        f"/files/{file_id}"
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
        f"/files/{file_id}/download"
    )

    assert download_response.status_code == 404

def test_download_nonexistant_file():
    response = client.get(
        f"/files/99999/download"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "File not found",
    }

def test_delete_nonexistant_file():
    response = client.delete(
            f"/files/99999"
        )
    
    assert response.status_code == 404
    assert response.json() == {
        "detail": "File not found",
    }

def test_download_when_storage_file_is_missing():
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

    response = client.get(f"files/{file_id}/download") 

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Stored file not found",
    }

def test_upload_empty_file():
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
    )

    assert response.status_code == 200

    data = response.json()

    assert data["filename"] == "empty.txt"
    assert data["size"] == 0
    assert len(data["sha256"]) == 64

def test_upload_exceeding_file_limit_rejection():
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
    response = client.post(
        "/files",
        files={
            "file": (
                "../../outside.txt",
                b"secret data",
                "text/plain",
            )
        },
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
    client.post(
        "/files",
        files={"file": ("first.txt", b"first file", "text/plain")},
    )
    client.post(
        "/files",
        files={"file": ("second.txt", b"second file", "text/plain")},
    )

    response = client.get("/files?limit=1")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 2

def test_list_files_offset():
    client.post(
        "/files",
        files={"file": ("first.txt", b"first file", "text/plain")},
    )
    client.post(
        "/files",
        files={"file": ("second.txt", b"second file", "text/plain")},
    )

    response = client.get("/files?limit=1&offset=1")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["offset"] == 1
    assert data["total"] == 2

