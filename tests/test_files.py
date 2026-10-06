from pathlib import Path
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import File

client = TestClient(app)

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

    assert len(files) == 2

    filenames = {file["filename"] for file in files}

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




