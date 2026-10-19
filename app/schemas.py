from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class HealthResponse(BaseModel):
    status: str
    database: str


class FileUploadResponse(BaseModel):
    id: int
    filename: str
    size: int
    sha256: str


class FileMetadataResponse(BaseModel):
    id: int
    filename: str
    size: int
    mime_type: str
    sha256: str
    created_at: datetime


class DeleteFileResponse(BaseModel):
    message: str
    id: int


class FileListResponse(BaseModel):
    items: list[FileMetadataResponse]
    limit: int
    offset: int
    total: int


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserRegisterResponse(BaseModel):
    id: int
    email: str


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str


class CurrentUserResponse(BaseModel):
    id: int
    email: str


class UploadSessionCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    total_size: int = Field(gt=0)
    mime_type: str = Field(default="application/octet-stream", max_length=100)


class UploadSessionResponse(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int
    status: str
    expires_at: datetime


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    total_size: int
    chunk_size: int
    total_chunks: int
    received_chunks: list[int]
    missing_chunks: list[int]
    status: str
    expires_at: datetime
