"""Face embedding schemas."""
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel


class FaceEmbeddingBase(BaseModel):
    person_id: UUID
    photo_id: Optional[UUID] = None
    model_version: str = "arcface_r50"
    quality_score: Optional[float] = None
    is_active: bool = True


class FaceEmbeddingCreate(FaceEmbeddingBase):
    embedding: bytes


class FaceEmbeddingResponse(BaseModel):
    id: UUID
    person_id: UUID
    photo_id: Optional[UUID] = None
    model_version: str
    quality_score: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingPersonItem(BaseModel):
    embedding_id: str
    person_id: str
    person_name: str
    embedding_bytes: str  # Base64 encoded string for JSON transport
    quality_score: Optional[float] = None
    created_at: Optional[str] = None
    photo_url: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    description: Optional[str] = None
    last_seen_location: Optional[str] = None
    last_seen_time: Optional[str] = None
    contact_info: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_phone: Optional[str] = None


class EmbeddingSyncResponse(BaseModel):
    full_sync: bool
    persons: List[EmbeddingPersonItem]
    removed_ids: List[str]
    sync_timestamp: str
