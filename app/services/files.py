import math
import uuid
import hashlib
from pathlib import Path
from fastapi import UploadFile
from typing import AsyncIterator
from datetime import timedelta, datetime, UTC

from sqlalchemy import insert, select, delete, update
from app.database import SessionLocal
from app.models import File, User, UploadSession

CHUNK_SIZE = 1024 * 1024
RESUMABLE_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MiB
UPLOAD_SESSION_TTL = timedelta(hours=24)

class FileTooLargeError(Exception):
    pass
class StorageQuotaExceededError(Exception):
    pass
class UploadSessionNotFoundError(Exception):
    pass
class UploadSessionExpiredError(Exception):
    pass
class InvalidChunkError(Exception):
    pass
class ChunkConflictError(Exception):
    pass

async def save_uploaded_file(file: UploadFile, storage_dir: Path, max_upload_size) -> tuple[str, Path, int, str]:
    filename = Path(file.filename or "unnamed").name

    storage_filename = str(uuid.uuid4())
    storage_path = storage_dir / storage_filename

    sha256 = hashlib.sha256()
    file_size = 0
    try:
        with storage_path.open("wb") as output_file:
            while chunk := await file.read(CHUNK_SIZE):
                file_size += len(chunk)

                if file_size > max_upload_size:
                    raise FileTooLargeError("File exceeds maximum allowed size")
            
                sha256.update(chunk)
                output_file.write(chunk)

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    return filename, storage_path, file_size, sha256.hexdigest()

def create_file_record(owner_id: int, filename: str, file_size: int, mime_type: str, file_hash: str, storage_path: Path, max_storage_size: int) -> int:
    db = SessionLocal()

    try:
        reservation = db.execute(update(User)
                                 .where(User.id == owner_id, User.storage_used + file_size <= max_storage_size)
                                 .values(storage_used = User.storage_used + file_size)
                                 .returning(User.id))
        if reservation.scalar_one_or_none() is None:
            raise StorageQuotaExceededError(
                "User storage quota exceeded"
            )
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
        user = (db.query(User)
                .filter(User.id == owner_id)
                .with_for_update()
                .one_or_none())
        
        if user is None:
            db.rollback()
            return None
        
        file = (db.query(File)
                .filter(File.id == file_id, File.owner_id == owner_id)
                .with_for_update()
                .one_or_none()
                )

        if file is None:
            db.rollback()
            return None

        storage_path = file.storage_path

        user.storage_used -= file.size

        db.delete(file)
        db.commit()

        return storage_path

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

def create_upload_session(owner_id: int, filename: str, total_size: int, mime_type:str, max_upload_size: int, max_storage_size: int) -> dict:
    filename = Path(filename.replace("\\","/")).name

    if not filename or filename in {".", ".."}:
        raise ValueError("Invalid filename")

    if total_size <= 0:
        raise ValueError("Upload size must be positive")

    if total_size > max_upload_size:
        raise ValueError("File exceeds maximum allowed size")

    chunk_size = RESUMABLE_CHUNK_SIZE
    total_chunks = int(math.ceil(total_size / chunk_size))
    upload_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + UPLOAD_SESSION_TTL

    db = SessionLocal()

    try:
        reservation = db.execute(
            update(User)
            .where(User.id == owner_id,
                   User.storage_used + User.reserved_storage + total_size <= max_storage_size,)
            .values(reserved_storage=User.reserved_storage+total_size)
            .returning(User.id)
        )
        if reservation.scalar_one_or_none() is None:
            raise StorageQuotaExceededError(
                "User storage quota exceeded"
            )
        session = UploadSession(
            id=upload_id,
            owner_id=owner_id,
            filename=filename,
            total_size=total_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            mime_type=mime_type or "application/octet-stream",
            status="in_progress",
            created_at=now,
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()

        return {
            "upload_id": upload_id,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "status": session.status,
            "expires_at": expires_at,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

async def save_upload_chunk(owner_id: int, upload_id: str, chunk_index: int, body: AsyncIterator[bytes], upload_dir: Path,
) -> dict:
    db = SessionLocal()
    try:
        session = db.execute(
            select(UploadSession)
            .where(UploadSession.id == upload_id, UploadSession.owner_id == owner_id,)
        ).scalar_one_or_none()

        if session is None:
            raise UploadSessionNotFoundError()

        now = datetime.now(UTC)
        expires_at = session.expires_at

        if expires_at <= now:
            raise UploadSessionExpiredError()

        if session.status != "in_progress":
            raise InvalidChunkError("Upload session is not active")

        if not 0 <= chunk_index < session.total_chunks:
            raise InvalidChunkError("Invalid chunk index")

        expected_size = min(
            session.chunk_size,
            session.total_size-chunk_index*session.chunk_size,
        )

        chunk_size = session.chunk_size

        total_chunks = session.total_chunks

    finally:
        db.close()

    upload_path = upload_dir / upload_id
    upload_path.mkdir(parents=True, exist_ok=True)
    destination = upload_path / f"{chunk_index}.chunk"
    temporary = upload_path / f".{uuid.uuid()}.tmp"

    digest = hashlib.sha256()

    received_size = 0

    try:
        with temporary.open("xb") as output:
            async for data in body:
                if not data:
                    continue

            received_size += len(data)

            if received_size > expected_size:
                raise InvalidChunkError("chunk exceeds expected size")

            digest.update(data)
            output.write(data)

        if received_size != expected_size:
            raise InvalidChunkError(f"Expected {expected_size} bytes, received {received_size}")

        chunk_hash = digest.hexdigest()

        db = SessionLocal()

        try:
            session = db.execute(select(UploadSession)
                .where(UploadSession.id == upload_id, UploadSession.owner_id == owner_id,)
                .with_for_update()
            ).scalar_one_or_none()

            if session is None:
                raise UploadSessionNotFoundError()

            now = datetime.now(UTC)
            expires_at = session.expires_at

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            if expires_at <= now:
                raise UploadSessionExpiredError()

            if session.status != "in_progress":
                raise InvalidChunkError("Upload session is not active")

            if destination.exists():
                existing_hash = hashlib.sha256()
                with destination.open("rb") as existing:
                    while data := existing.read(1024 * 1024):
                        existing_hash.update(data)

                if existing_hash.hexdigest()!= chunk_hash:
                    raise ChunkConflictError("this chunk index already contains different data")
                else:
                    temporary.replace(destination)

                db.commit()

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "size": received_size,
            "sha256": chunk_hash,
            "status": "received",
        }
    finally:
        temporary.unlink(missing_ok=True)