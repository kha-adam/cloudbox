from pathlib import Path

from fastapi import APIRouter, File as FastAPIFile, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.database import SessionLocal
from app.config import settings
from app.models import File
from app.services.files import (
    FileTooLargeError,
    save_uploaded_file,
    create_file_record,
    get_file,
    delete_file_record,
)
from app.schemas import (
    DeleteFileResponse,
    FileMetadataResponse,
    FileUploadResponse,
)
router = APIRouter()

STORAGE_DIR = Path(settings.storage_dir)
STORAGE_DIR.mkdir(exist_ok=True)

@router.post("/files", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = FastAPIFile(...)):
    try:
        filename, storage_path, file_size, file_hash = await save_uploaded_file(file, STORAGE_DIR, max_upload_size=settings.max_upload_size,)

    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    try:
        file_id = create_file_record(
            filename=filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_hash=file_hash,
            storage_path=storage_path,
        )

        return {
            "id": file_id,
            "filename": filename,
            "size": file_size,
            "sha256": file_hash,
        }

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

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
        file = get_file(file_id)

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
        file = get_file(file_id)

        if file is None:
            raise HTTPException(
                status_code=404,
                detail="File not found",
            )

        storage_path = Path(file.storage_path)

        if storage_path.exists():
            storage_path.unlink()

        delete_file_record(file_id)

        return {
            "message": "File deleted",
            "id": file_id,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
