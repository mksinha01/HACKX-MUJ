"""Sighting schemas."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class SightingCreate(BaseModel):
    """Create a sighting event from Edge Agent."""
    person_id: UUID
    camera_id: UUID
    similarity_score: float
    confidence_level: str = "POSSIBLE"
    num_frames_matched: Optional[int] = None
    camera_location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    detected_at: datetime


class SightingReview(BaseModel):
    """Operator review of a sighting."""
    status: Optional[str] = None  # CONFIRMED | REJECTED
    review_notes: Optional[str] = None


class SightingResponse(BaseModel):
    """Sighting data in responses."""
    id: UUID
    person_id: UUID
    person_name: Optional[str] = None
    agent_id: UUID
    camera_id: UUID
    similarity_score: float
    confidence_level: str
    num_frames_matched: Optional[int] = None
    face_crop_path: Optional[str] = None
    full_frame_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    camera_location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    detected_at: datetime
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineEntry(BaseModel):
    """Single entry in a sighting timeline (last-seen feature)."""
    sighting_id: UUID
    camera_name: str
    camera_location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    detected_at: datetime
    similarity_score: float
    status: str


class PersonTimeline(BaseModel):
    """Complete sighting timeline for a missing person."""
    person_id: UUID
    person_name: str
    entries: List[TimelineEntry]
    last_seen_camera: Optional[str] = None
    last_seen_time: Optional[datetime] = None
