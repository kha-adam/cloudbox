import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, File as FastAPIFile, UploadFile
from sqlalchemy import insert

from app.database import SessionLocal
from app.models import File

router = APIRouter()

STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)

@router.post("/files")
async def upload_file(file: UploadFile = FastAPIFile(...)):
    file_data = await file.read()
    sha256 = hashlib.sha256(file_data).hexdigest()
    filename = file.filename or "unnamed"
    storage_path = STORAGE_DIR / filename
    storage_path.write_bytes(file_data)

    db = SessionLocal()

    try:
        statement = insert(File).values(
            filename = filename,
            size = len(file_data),
            mime_type = file.content_type or "application/octet-stream",
            sha256 = sha256,
            storage_path = str(storage_path),
        )
        result = db.execute(statement)
        db.commit()

        field_id = result.inserted_primary_key[0]

        return {
            "id": field_id,
            "filename": filename,
            "size": len(file_data),
            "sha256": sha256,
        }
    except Exception:
        db.rollback()
        raise

    finally:
        db.close()