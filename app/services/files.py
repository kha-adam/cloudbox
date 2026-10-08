import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from sqlalchemy import insert, select, delete
from app.database import SessionLocal
from app.models import File

CHUNK_SIZE = 1024 * 1024

class FileTooLargeError(Exception):
    pass

async def save_uploaded_file(file: UploadFile, storage_dir: Path, max_upload_size) -> tuple[str, Path, int, str]:
    filename = file.filename or "unnamed"

    storage_filename = str(uuid.uuid4())
    storage_path = storage_dir / storage_filename

    sha256 = hashlib.sha256()
    file_size = 0
    try:
        with storage_path.open("wb") as output_file:
            while chunk := await file.read(CHUNK_SIZE):
                file_size += len(chunk)

                if file_size > max_upload_size:
                    storage_path.unlink()
                    await file.close()
                    raise FileTooLargeError("File exceeds maximum allowed size")
            
                sha256.update(chunk)
                output_file.write(chunk)
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return filename, storage_path, file_size, sha256.hexdigest()

def create_file_record(owner_id: int, filename: str, file_size: int, mime_type: str, file_hash: str, storage_path: Path) -> int:
    db = SessionLocal()

    try:
        statement = insert(File).values(
            owner_id=owner_id,
            filename=filename,
            size=file_size,
            mime_type=mime_type,
            sha256=file_hash,
            storage_path=str(storage_path),
        )

        result = db.execute(statement)
        db.commit()

        return result.inserted_primary_key[0]

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()    

def get_file(file_id: int, owner_id: int) -> File | None:
    db = SessionLocal()

    try:
        statement = select(File).where(File.id == file_id,
                                        File.owner_id == owner_id)
        result = db.execute(statement)

        return result.scalar_one_or_none()

    finally:
        db.close()

def list_files(limit: int, offset: int, owner_id = int)->tuple[list[File], int]:
    db = SessionLocal()

    try:
        total = db.query(File).filter(File.owner_id == owner_id).count()

        files = (db.query(File)
        .filter(File.owner_id == owner_id)
        .order_by(File.created_at.desc(), File.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
        )
        return files, total
    
    finally:
        db.close()

def delete_file_record(file_id: int, owner_id: int) -> None:
    db = SessionLocal()

    try:
        statement = delete(File).where(File.id == file_id,
                                       File.owner_id == owner_id)

        db.execute(statement)
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()



