import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from sqlalchemy import insert
from app.database import SessionLocal
from app.models import File

CHUNK_SIZE = 1024 * 1024

async def save_uploaded_file(file: UploadFile, storage_dir: Path) -> tuple[str, Path, int, str]:
    filename = file.filename or "unnamed"

    safe_filename = Path(filename).name
    storage_filename = f"{uuid.uuid4}_{safe_filename}"
    storage_path = storage_dir / storage_filename

    sha256 = hashlib.sha256()
    file_size = 0

    with storage_path.open("wb") as output_file:
        while chunk := await file.read(CHUNK_SIZE):
            output_file.write(chunk)
            sha256.update(chunk)
            file_size += len(chunk)

    await file.close()

    return filename, storage_path, file_size, sha256.hexdigest()

def create_file_record(filename: str, file_size: int, mime_type: str, file_hash: str, storage_path: Path) -> int:
    db = SessionLocal()

    try:
        statement = insert(File).values(
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


