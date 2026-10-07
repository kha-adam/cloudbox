from datetime import datetime, UTC

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False,)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False,)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False,)

    files: Mapped[list["File"]] = relationship(back_populates="owner")
    

class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[int] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False
    )

    owner: Mapped["User | None"] = relationship(
        back_populates="files",
    )

