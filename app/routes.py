import hashlib
import uuid
from pathlib import Path
import os

from fastapi import APIRouter, File as FastAPIFile, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import insert, select, delete

from app.database import SessionLocal
from app.models import File
from app.schemas import (
    DeleteFileResponse,
    FileMetadataResponse,
    FileUploadResponse,
)
router = APIRouter()

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage"))
STORAGE_DIR.mkdir(exist_ok=True)

CHUNK_SIZE = 1024 * 1024

@router.post("/files", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = FastAPIFile(...)):
    filename = file.filename or "unnamed"
    safe_filename = Path(filename).name
    storage_filename = f"{uuid.uuid4()}_{safe_filename}"
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

@router.get("/files", response_model=list[FileMetadataResponse])
def list_files():
    db = SessionLocal()

    try:
        statement = select(File).order_by(File.created_at.desc())
        results = db.execute(statement)

        files = results.scalars().all()

        return [
            {
                "id": file.id,
                "filename": file.filename,
                "size": file.size,
                "mime_type": file.mime_type,
                "sha256": file.sha256,
                "created_at": file.created_at,
            } 
            for file in files
        ]
    finally:
        db.close()

@router.get("/files/{file_id}/download")
def download_file(file_id: int):
    db = SessionLocal()

    try:
        statement = select(File).where(File.id == file_id)
        result = db.execute(statement)

        file = result.scalar_one_or_none()

        if file is None:
            raise HTTPException(
                status_code=404,
                detail="File not found",
            )
        
        storage_path = Path(file.storage_path)

        if not storage_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Stored file not found",
            )

        return FileResponse(
            path=storage_path,
            media_type=file.mime_type,
            filename=file.filename
        )
    finally:
        db.close()

@router.delete("/files/{file_id}", response_model=DeleteFileResponse)
def delete_file(file_id: int):
    db = SessionLocal()

    try:
        statement = select(File).where(File.id == file_id)
        result = db.execute(statement)

        file = result.scalar_one_or_none()

        if file is None:
            raise HTTPException(
                status_code=404,
                detail="File not found",
            )

        storage_path = Path(file.storage_path)

        if storage_path.exists():
            storage_path.unlink()

        db.execute(
            delete(File).where(File.id == file_id)
            )
        db.commit()

        return {
            "message": "File deleted",
            "id": file_id,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()