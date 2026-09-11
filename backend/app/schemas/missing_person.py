"""Missing Person report schemas with FIR verification support."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class MissingPersonCreate(BaseModel):
    """Create a new missing person report with FIR details."""
    full_name: str = Field(..., max_length=255)
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Optional[str] = Field(None, max_length=20)
    height_cm: Optional[int] = Field(None, ge=30, le=300)
    description: Optional[str] = Field(None, max_length=2000)
    last_seen_location: Optional[str] = Field(None, max_length=500)
    last_seen_time: Optional[datetime] = None
    contact_info: Optional[str] = Field(None, max_length=500)
    # FIR fields — required for report submission
    fir_number: str = Field(..., min_length=3, max_length=100, description="FIR number from police station e.g. FIR/2026/1234")
    fir_police_station: str = Field(..., min_length=2, max_length=255, description="Name of the police station where FIR was filed")
    fir_date: Optional[datetime] = Field(None, description="Date when FIR was filed")


class MissingPersonUpdate(BaseModel):
    """Update a missing person report."""
    full_name: Optional[str] = Field(None, max_length=255)
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Optional[str] = Field(None, max_length=20)
    height_cm: Optional[int] = Field(None, ge=30, le=300)
    description: Optional[str] = Field(None, max_length=2000)
    last_seen_location: Optional[str] = Field(None, max_length=500)
    last_seen_time: Optional[datetime] = None
    contact_info: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None
    # FIR fields — can be updated for resubmission
    fir_number: Optional[str] = Field(None, max_length=100)
    fir_police_station: Optional[str] = Field(None, max_length=255)
    fir_date: Optional[datetime] = None


class PhotoResponse(BaseModel):
    """Photo data in responses."""
    id: UUID
    original_path: str
    face_crop_path: Optional[str] = None
    is_primary: bool
    processing_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MissingPersonResponse(BaseModel):
    """Full missing person report response with FIR details."""
    id: UUID
    user_id: UUID
    full_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[int] = None
    description: Optional[str] = None
    last_seen_location: Optional[str] = None
    last_seen_time: Optional[datetime] = None
    status: str
    contact_info: Optional[str] = None
    # FIR fields
    fir_number: Optional[str] = None
    fir_police_station: Optional[str] = None
    fir_date: Optional[datetime] = None
    fir_status: Optional[str] = None
    fir_document_path: Optional[str] = None
    fir_rejection_reason: Optional[str] = None
    fir_verified_at: Optional[datetime] = None
    # Timestamps
    created_at: datetime
    updated_at: datetime
    photos: List[PhotoResponse] = []

    model_config = {"from_attributes": True}


class MissingPersonListResponse(BaseModel):
    """Paginated list of reports."""
    items: List[MissingPersonResponse]
    total: int
    page: int
    per_page: int
