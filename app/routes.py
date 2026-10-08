from pathlib import Path

from fastapi import APIRouter, File as FastAPIFile, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi import Depends
from sqlalchemy import select, func

from app.database import SessionLocal
from app.config import settings
from app.models import File, User
from app.dependencies import get_current_user
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

@router.get("/files", response_model=FileListResponse)
def list_files(limit: int = Query(default=50, ge=1, le=100), 
               offset: int = Query(default=0, ge=0)):
    db = SessionLocal()

    try:
        total = db.scalar(select(func.count()).select_from(File))
        statement = (
            select(File)
            .order_by(File.created_at.desc())
            .offset(offset)
            .limit(limit)
            )
        results = db.execute(statement)

        files = results.scalars().all()

        return {
            "items": [
                {
                    "id": file.id,
                    "filename": file.filename,
                    "size": file.size,
                    "mime_type": file.mime_type,
                    "sha256": file.sha256,
                    "created_at": file.created_at,
                } 
                for file in files
            ],
            "limit": limit,
            "offset": offset,
            "total": total,
            }
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

@router.post("/auth/register", response_model=UserRegisterResponse, status_code=201)
def register_user(user: UserRegisterRequest):
    email=user.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required"
        )
    if not user.password:
        raise HTTPException(
            status_code=400,
            detail="Password is required",
        )

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