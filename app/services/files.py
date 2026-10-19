import hashlib
import math
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import insert, select, update

from app.database import SessionLocal
from app.models import File, UploadSession, User

CHUNK_SIZE = 1024 * 1024
RESUMABLE_CHUNK_SIZE = 5 * 1024 * 1024
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


async def save_uploaded_file(
    file: UploadFile, storage_dir: Path, max_upload_size
) -> tuple[str, Path, int, str]:
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


def create_file_record(
    owner_id: int,
    filename: str,
    file_size: int,
    mime_type: str,
    file_hash: str,
    storage_path: Path,
    max_storage_size: int,
) -> int:
    db = SessionLocal()

    try:
        reservation = db.execute(
            update(User)
            .where(
                User.id == owner_id, User.storage_used + file_size <= max_storage_size
            )
            .values(storage_used=User.storage_used + file_size)
            .returning(User.id)
        )
        if reservation.scalar_one_or_none() is None:
            raise StorageQuotaExceededError("User storage quota exceeded")
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
        statement = select(File).where(File.id == file_id, File.owner_id == owner_id)
        result = db.execute(statement)

        return result.scalar_one_or_none()

    finally:
        db.close()


def list_files(limit: int, offset: int, owner_id=int) -> tuple[list[File], int]:
    db = SessionLocal()

    try:
        total = db.query(File).filter(File.owner_id == owner_id).count()

        files = (
            db.query(File)
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
        user = (
            db.query(User).filter(User.id == owner_id).with_for_update().one_or_none()
        )

        if user is None:
            db.rollback()
            return None

        file = (
            db.query(File)
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


def create_upload_session(
    owner_id: int,
    filename: str,
    total_size: int,
    mime_type: str,
    max_upload_size: int,
    max_storage_size: int,
) -> dict:
    filename = Path(filename.replace("\\", "/")).name

    if not filename or filename in {".", ".."}:
        raise ValueError("Invalid filename")

    if total_size <= 0:
        raise ValueError("Upload size must be positive")

    if total_size > max_upload_size:
        raise FileTooLargeError("File exceeds maximum allowed size")

    chunk_size = RESUMABLE_CHUNK_SIZE
    total_chunks = math.ceil(total_size / chunk_size)
    upload_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + UPLOAD_SESSION_TTL

    db = SessionLocal()

    try:
        reservation = db.execute(
            update(User)
            .where(
                User.id == owner_id,
                User.storage_used + User.reserved_storage + total_size
                <= max_storage_size,
            )
            .values(reserved_storage=User.reserved_storage + total_size)
            .returning(User.id)
        )
        if reservation.scalar_one_or_none() is None:
            raise StorageQuotaExceededError("User storage quota exceeded")
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


async def save_upload_chunk(
    owner_id: int,
    upload_id: str,
    chunk_index: int,
    body: AsyncIterator[bytes],
    upload_dir: Path,
) -> dict:
    db = SessionLocal()
    try:
        session = db.execute(
            select(UploadSession).where(
                UploadSession.id == upload_id,
                UploadSession.owner_id == owner_id,
            )
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
            session.total_size - chunk_index * session.chunk_size,
        )

    finally:
        db.close()

    upload_path = upload_dir / upload_id
    upload_path.mkdir(parents=True, exist_ok=True)
    destination = upload_path / f"{chunk_index}.chunk"
    temporary = upload_path / f".{uuid.uuid4()}.tmp"

    digest = hashlib.sha256()

    received_size = 0

    try:
        with temporary.open("xb") as output:
            async for data in body:
                if not data:
                    continue

                received_size += len(data)

                if received_size > expected_size:
                    raise InvalidChunkError("Chunk exceeds expected size")

                digest.update(data)
                output.write(data)

        if received_size != expected_size:
            raise InvalidChunkError(
                f"Expected {expected_size} bytes, received {received_size}"
            )

        chunk_hash = digest.hexdigest()

        db = SessionLocal()

        try:
            session = db.execute(
                select(UploadSession)
                .where(
                    UploadSession.id == upload_id,
                    UploadSession.owner_id == owner_id,
                )
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

                if existing_hash.hexdigest() != chunk_hash:
                    raise ChunkConflictError(
                        "This chunk index already contains different data"
                    )
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


def get_upload_status(
    owner_id: int,
    upload_id: str,
    upload_dir: Path,
) -> dict:
    db = SessionLocal()

    try:
        session = db.execute(
            select(UploadSession).where(
                UploadSession.id == upload_id,
                UploadSession.owner_id == owner_id,
            )
        ).scalar_one_or_none()

        if session is None:
            raise UploadSessionNotFoundError()

        upload_path = upload_dir / upload_id

        received_chunks = (
            sorted(
                int(path.name.removesuffix(".chunk"))
                for path in upload_path.glob("*.chunk")
                if path.name.removesuffix(".chunk").isdigit()
                and 0 <= int(path.name.removesuffix(".chunk")) < session.total_chunks
                and path.stat().st_size
                == min(
                    session.chunk_size,
                    session.total_size
                    - int(path.name.removesuffix(".chunk")) * session.chunk_size,
                )
            )
            if upload_path.exists()
            else []
        )

        received_set = set(received_chunks)
        missing_chunks = [
            index for index in range(session.total_chunks) if index not in received_set
        ]

        now = datetime.now(UTC)
        expires_at = session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        status = session.status
        if expires_at <= now and status == "in_progress":
            status = "expired"

        return {
            "upload_id": session.id,
            "filename": session.filename,
            "total_size": session.total_size,
            "chunk_size": session.chunk_size,
            "total_chunks": session.total_chunks,
            "received_chunks": received_chunks,
            "missing_chunks": missing_chunks,
            "status": status,
            "expires_at": expires_at,
        }

    finally:
        db.close()


def validate_upload_chunks(session: UploadSession, upload_dir: Path) -> list[Path]:
    session_dir = upload_dir / session.id
    chunk_paths = []

    for index in range(session.total_chunks):
        chunk_path = session_dir / f"{index}.chunk"

        if not chunk_path.is_file():
            raise InvalidChunkError(f"Missing chunk {index}")

        expected_size = min(
            session.chunk_size, session.total_size - index * session.chunk_size
        )

        if chunk_path.stat().st_size != expected_size:
            raise InvalidChunkError(f"Chunk {index} has incorrect size")

        chunk_paths.append(chunk_path)

    return chunk_paths


def complete_upload(
    owner_id: int, upload_id: str, upload_dir: Path, storage_dir: Path
) -> dict:
    db = SessionLocal()
    temporary = None
    final_path = None
    moved_final_file = False

    try:
        session = db.execute(
            select(UploadSession)
            .where(UploadSession.id == upload_id, UploadSession.owner_id == owner_id)
            .with_for_update()
        ).scalar_one_or_none()

        if session is None:
            raise UploadSessionNotFoundError()

        if session.status == "completed":
            file_record = db.execute(
                select(File).where(
                    File.owner_id == owner_id,
                    File.storage_path == str(storage_dir / upload_id),
                )
            ).scalar_one_or_none()

            if file_record is None:
                raise InvalidChunkError(
                    "Upload is marked completed but its file record is missing"
                )
            return {
                "id": file_record.id,
                "filename": file_record.filename,
                "size": file_record.size,
                "sha256": file_record.sha256,
            }

        now = datetime.now(UTC)
        expires_at = session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= now:
            raise UploadSessionExpiredError()

        if session.status != "in_progress":
            raise InvalidChunkError("Upload session is not active")

        chunk_paths = validate_upload_chunks(session, upload_dir)

        storage_dir.mkdir(parents=True, exist_ok=True)

        final_path = storage_dir / upload_id

        temporary = storage_dir / f".{upload_id}-temporary.tmp"

        digest = hashlib.sha256()

        assembled_size = 0

        with temporary.open("xb") as output:
            for chunk_path in chunk_paths:
                with chunk_path.open("rb") as chunk:
                    while data := chunk.read(1024 * 1024):
                        output.write(data)
                        digest.update(data)
                        assembled_size += len(data)
        if assembled_size != session.total_size:
            raise InvalidChunkError("Assembled file size does not atch expected size")

        final_hash = digest.hexdigest()

        user = db.execute(
            select(User).where(User.id == owner_id).with_for_update()
        ).scalar_one()

        # final_path.parent.mkdir(parents=True, exist_ok = True)
        temporary.replace(final_path)

        moved_final_file = True

        file_record = File(
            owner_id=owner_id,
            filename=session.filename,
            size=assembled_size,
            mime_type=session.mime_type,
            sha256=final_hash,
            storage_path=str(final_path),
        )
        db.add(file_record)

        user.storage_used += assembled_size
        user.reserved_storage -= session.total_size
        session.status = "completed"

        db.commit()
        db.refresh(file_record)

        return {
            "id": file_record.id,
            "filename": file_record.filename,
            "size": file_record.size,
            "sha256": file_record.sha256,
        }

    except Exception:
        db.rollback()

        if moved_final_file and final_path is not None:
            final_path.unlink(missing_ok=True)
        raise

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        db.close()


def cleanup_expired_uploads(upload_dir: Path, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    removed_count = 0
    db = SessionLocal()
    try:
        expired_sessions = (
            db.execute(
                select(UploadSession)
                .where(
                    UploadSession.status == "in_progress",
                    UploadSession.expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for session in expired_sessions:
            session_dir = upload_dir / session.id
            if session_dir.exists():
                shutil.rmtree(session_dir)

            user = db.execute(
                select(User).where(User.id == session.owner_id).with_for_update()
            ).scalar_one_or_none()

            if user is None:
                continue

            user.reserved_storage = max(0, user.reserved_storage - session.total_size)

            db.delete(session)
            removed_count += 1

        db.commit()
        return removed_count

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
