from pathlib import Path
import time

from fastapi import APIRouter, File as FastAPIFile, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi import Depends

from app.config import settings
from app.models import File, User
from app.dependencies import get_current_user
from app.services.files import list_files as list_files_service
from app.services.files import StorageQuotaExceededError
from app.services.files import (
    FileTooLargeError,
    save_uploaded_file,
    create_file_record,
    get_file,
    delete_file_record,
)
from app.services.users import get_user_by_email, create_user
from app.security import hash_password, verify_password, create_access_token, decode_access_token
from app.schemas import (
    DeleteFileResponse,
    FileMetadataResponse,
    FileUploadResponse,
    FileListResponse,
    UserRegisterRequest,
    UserRegisterResponse,
    UserLoginRequest,
    UserLoginResponse,
    CurrentUserResponse,
)
router = APIRouter()

STORAGE_DIR = Path(settings.storage_dir)
STORAGE_DIR.mkdir(exist_ok=True)

@router.post("/files", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = FastAPIFile(...), 
                      current_user: User = Depends(get_current_user)):
    upload_start = time.perf_counter()
    try:
        storage_start = time.perf_counter()
        filename, storage_path, file_size, file_hash = await save_uploaded_file(file, STORAGE_DIR, max_upload_size=settings.max_upload_size,)
        storage_ms = (time.perf_counter() - storage_start) * 1000
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    try:
        database_start = time.perf_counter()
        file_id = create_file_record(
            owner_id=current_user.id,
            filename=filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_hash=file_hash,
            storage_path=storage_path,
            max_storage_size=settings.max_storage_per_user
        )
        database_ms = (time.perf_counter() - database_start)
    except StorageQuotaExceededError as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    total_ms = (time.perf_counter() - upload_start) * 1000
    print(
        f"upload_timing file_size={file_size} "
        f"storage_ms={storage_ms:.2f} "
        f"database_ms={database_ms:.2f} "
        f"total_ms={total_ms:.2f}",
        flush=True,
    )
    return {
        "id": file_id,
        "filename": filename,
        "size": file_size,
        "sha256": file_hash,
    }


@router.get("/files", response_model=FileListResponse)
def list_files(limit: int = Query(default=50, ge=1, le=100), 
               offset: int = Query(default=0, ge=0),
               current_user: User = Depends(get_current_user)):
    files, total = list_files_service(owner_id=current_user.id,
                                      limit=limit,
                                      offset=offset,)
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
        path=storage_path,
        media_type=file.mime_type,
        filename=file.filename
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

        logging .getLogger(__name__).exception(
            "Could not remove stored file %s", path
        )

    return {
        "message": "File deleted",
        "id": file_id,
    }

@router.post("/auth/register", response_model=UserRegisterResponse, status_code=201)
def register_user(user: UserRegisterRequest):
    email = str(user.email).strip().lower()

    existing_user = get_user_by_email(email)

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

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
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not verify_password(
        user.password,
        existing_user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

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