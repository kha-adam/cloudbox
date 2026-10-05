import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, File as FastAPIFile, UploadFile
from sqlalchemy import insert

from app.database import SessionLocal
from app.models import File

router = APIRouter()

STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)

CHUNK_SIZE = 1024 * 1024

@router.post("/files")
async def upload_file(file: UploadFile = FastAPIFile(...)):
    filename = file.filename or "unnamed"

    storage_filename = f"{uuid.uuid4()}_{filename}"
    storage_path = STORAGE_DIR / storage_filename

    sha256 = hashlib.sha256()
    file_size = 0

    with storage_path.open("wb") as output_file:
        while chunk := await file.read(CHUNK_SIZE):
            output_file.write(chunk)
            sha256.update(chunk)
            file_size += len(chunk)

    db = SessionLocal()

    try:
        statement = insert(File).values(
            filename = filename,
            size = file_size,
            mime_type = file.content_type or "application/octet-stream",
            sha256 = sha256.hexdigest(),
            storage_path = str(storage_path),
        )
        result = db.execute(statement)
        db.commit()

        field_id = result.inserted_primary_key[0]

        return {
            "id": field_id,
            "filename": filename,
            "size": file_size,
            "sha256": sha256.hexdigest(),
        }
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise

    finally:
        db.close()