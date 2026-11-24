"""Pydantic request / response models. ORM objects never leave the API layer directly."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import get_settings

# ---------- auth ----------


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(v) > 128:
        raise ValueError("Password must be at most 128 characters")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("Password must contain at least one letter and one number")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None


# ---------- documents ----------

DocumentStatus = Literal["pending_upload", "queued", "processing", "ready", "failed"]


class UploadUrlIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    file_size_bytes: int = Field(gt=0)
    vehicle_model: str | None = Field(default=None, max_length=80)
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("filename")
    @classmethod
    def _pdf(cls, v: str) -> str:
        if not v.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are allowed")
        return v

    @field_validator("file_size_bytes")
    @classmethod
    def _size(cls, v: int) -> int:
        max_mb = get_settings().MAX_UPLOAD_MB
        if v > max_mb * 1024 * 1024:
            raise ValueError(f"File exceeds the {max_mb} MB limit")
        return v


class UploadUrlOut(BaseModel):
    document_id: uuid.UUID
    path: str
    token: str | None
    mode: Literal["supabase", "local"]
    upload_url: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    display_name: str
    original_filename: str
    vehicle_model: str
    model_year: str | None
    uploaded_at: datetime
    processed_at: datetime | None
    status: DocumentStatus
    status_detail: str | None
    page_count: int | None
    chunk_count: int
    file_size_bytes: int
    owner_is_me: bool


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
    ready_count: int


class DocumentPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    vehicle_model: str | None = Field(default=None, min_length=1, max_length=80)


class ViewUrlOut(BaseModel):
    url: str
    expires_in: int


class VehicleList(BaseModel):
    models: list[str]


# ---------- chat ----------


class SourceOut(BaseModel):
    n: int
    document_id: uuid.UUID
    document_name: str
    vehicle_model: str
    page: int
    snippet: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] | None
    intent: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationList(BaseModel):
    items: list[ConversationOut]
    total: int


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MessageIn(BaseModel):
    content: str = Field(min_length=1)
    regenerate: bool = False

    @field_validator("content")
    @classmethod
    def _len(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        limit = get_settings().MAX_MESSAGE_CHARS
        if len(v) > limit:
            raise ValueError(f"Message must be at most {limit} characters")
        return v


class ChatAnswer(BaseModel):
    message_id: uuid.UUID
    user_message_id: uuid.UUID
    content: str
    sources: list[SourceOut]
    intent: str | None
    conversation_title: str


class HealthOut(BaseModel):
    status: str
    db: bool
    detail: dict[str, Any] | None = None
