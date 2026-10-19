# ruff: noqa: B008
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi import File as FastAPIFile
from fastapi.responses import FileResponse

from app.config import settings
from app.dependencies import get_current_user
from app.models import User
from app.schemas import (
    CurrentUserResponse,
    DeleteFileResponse,
    FileListResponse,
    FileUploadResponse,
    UploadSessionCreateRequest,
    UploadSessionResponse,
    UploadStatusResponse,
    UserLoginRequest,
    UserLoginResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from app.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.files import (
    ChunkConflictError,
    FileTooLargeError,
    InvalidChunkError,
    StorageQuotaExceededError,
    UploadSessionExpiredError,
    UploadSessionNotFoundError,
    complete_upload,
    create_file_record,
    create_upload_session,
    delete_file_record,
    get_file,
    get_upload_status,
    save_upload_chunk,
    save_uploaded_file,
)
from app.services.files import list_files as list_files_service
from app.services.users import create_user, get_user_by_email

router = APIRouter()

STORAGE_DIR = Path(settings.storage_dir)
STORAGE_DIR.mkdir(exist_ok=True)


@router.post("/files", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = FastAPIFile(...), current_user: User = Depends(get_current_user)
):
    try:
        filename, storage_path, file_size, file_hash = await save_uploaded_file(
            file,
            STORAGE_DIR,
            max_upload_size=settings.max_upload_size,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    try:
        file_id = create_file_record(
            owner_id=current_user.id,
            filename=filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_hash=file_hash,
            storage_path=storage_path,
            max_storage_size=settings.max_storage_per_user,
        )
    except StorageQuotaExceededError as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    return {
        "id": file_id,
        "filename": filename,
        "size": file_size,
        "sha256": file_hash,
    }


@router.get("/files", response_model=FileListResponse)
def list_files(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    files, total = list_files_service(
        owner_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": files,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/files/{file_id}/download")
def download_file(file_id: int, current_user: User = Depends(get_current_user)):
    file = get_file(file_id, current_user.id)

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
        path=storage_path, media_type=file.mime_type, filename=file.filename
    )


@router.delete("/files/{file_id}", response_model=DeleteFileResponse)
def delete_file(file_id: int, current_user: User = Depends(get_current_user)):
    storage_path = delete_file_record(file_id=file_id, owner_id=current_user.id)

    if storage_path is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    path = Path(storage_path)

    try:
        path.unlink(missing_ok=True)

    except OSError:
        import logging

        logging.getLogger(__name__).exception("Could not remove stored file %s", path)

    return {
        "message": "File deleted",
        "id": file_id,
    }


@router.post("/uploads", response_model=UploadSessionResponse, status_code=201)
def start_upload(
    request: UploadSessionCreateRequest, current_user: User = Depends(get_current_user)
):
    try:
        return create_upload_session(
            owner_id=current_user.id,
            filename=request.filename,
            total_size=request.total_size,
            mime_type=request.mime_type,
            max_upload_size=settings.max_upload_size,
            max_storage_size=settings.max_storage_per_user,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc
    except StorageQuotaExceededError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.put("/uploads/{upload_id}/chunks/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    upload_dir = STORAGE_DIR / "uploads"

    try:
        return await save_upload_chunk(
            owner_id=current_user.id,
            upload_id=upload_id,
            chunk_index=chunk_index,
            body=request.stream(),
            upload_dir=upload_dir,
        )

    except UploadSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found",
        ) from exc

    except UploadSessionExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail="Upload session has expired",
        ) from exc

    except ChunkConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except InvalidChunkError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/uploads/{upload_id}",
    response_model=UploadStatusResponse,
)
def upload_status(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        return get_upload_status(
            owner_id=current_user.id,
            upload_id=upload_id,
            upload_dir=STORAGE_DIR / "uploads",
        )
    except UploadSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found",
        ) from exc


@router.post("/uploads/{upload_id}/complete")
def finish_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        return complete_upload(
            owner_id=current_user.id,
            upload_id=upload_id,
            upload_dir=STORAGE_DIR / "uploads",
            storage_dir=STORAGE_DIR,
        )

    except UploadSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found",
        ) from exc

    except UploadSessionExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail="Upload session has expired",
        ) from exc

    except InvalidChunkError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/auth/register", response_model=UserRegisterResponse, status_code=201)
def register_user(user: UserRegisterRequest):
    email = str(user.email).strip().lower()

    existing_user = get_user_by_email(email)

    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = hash_password(user.password)

    user_id = create_user(email=email, password_hash=password_hash)

    return {
        "id": user_id,
        "email": email,
    }


@router.post("/auth/login", response_model=UserLoginResponse)
def login_user(user: UserLoginRequest):
    email = user.email.strip().lower()

    existing_user = get_user_by_email(email)

    if existing_user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(user.password, existing_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(existing_user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/auth/me", response_model=CurrentUserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
    }
