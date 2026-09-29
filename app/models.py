"""Database models: User, Scan, ScanResult."""
from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    scans: Mapped[list["Scan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}>"


class ScanStatus:
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Scan(db.Model):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ScanStatus.PROCESSING)
    error_message: Mapped[str | None] = mapped_column(Text)
    total_rows: Mapped[int] = mapped_column(default=0)
    malicious_count: Mapped[int] = mapped_column(default=0)
    benign_count: Mapped[int] = mapped_column(default=0)
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="scans")
    results: Mapped[list["ScanResult"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ScanResult.row_index",
        lazy="dynamic",
    )

    @property
    def malicious_ratio(self) -> float:
        return self.malicious_count / self.total_rows if self.total_rows else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "notes": self.notes,
            "status": self.status,
            "error_message": self.error_message,
            "total_rows": self.total_rows,
            "malicious_count": self.malicious_count,
            "benign_count": self.benign_count,
            "malicious_ratio": round(self.malicious_ratio, 4),
            "model_version": self.model_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Scan {self.id} {self.filename}>"


class ScanResult(db.Model):
    __tablename__ = "scan_results"
    __table_args__ = (Index("ix_scan_results_scan_label", "scan_id", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int]
    label: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float]
    features: Mapped[dict] = mapped_column(JSON)

    scan: Mapped[Scan] = relationship(back_populates="results")

    def to_dict(self) -> dict:
        return {
            "row": self.row_index,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "features": self.features,
        }
