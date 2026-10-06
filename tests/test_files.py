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