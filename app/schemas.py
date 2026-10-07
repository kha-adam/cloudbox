from datetime import datetime

from pydantic import BaseModel

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