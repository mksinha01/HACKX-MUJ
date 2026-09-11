"""CRUD operations for sightings table."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sighting import Sighting
from app.models.camera import Camera
from app.models.missing_person import MissingPerson
from app.crud.face_embedding import deactivate_embeddings_for_person
from app.schemas.sighting import SightingCreate


# ── Sightings ──

async def create_sighting(
    db: AsyncSession, agent_id: UUID, data: SightingCreate,
    face_crop_path: Optional[str] = None,
    full_frame_path: Optional[str] = None,
) -> Sighting:
    """Create a new sighting event from Edge Agent detection."""
    sighting = Sighting(
        agent_id=agent_id,
        person_id=data.person_id,
        camera_id=data.camera_id,
        similarity_score=data.similarity_score,
        confidence_level=data.confidence_level,
        num_frames_matched=data.num_frames_matched,
        camera_location=data.camera_location,
        latitude=data.latitude,
        longitude=data.longitude,
        detected_at=data.detected_at,
        face_crop_path=face_crop_path,
        full_frame_path=full_frame_path,
    )
    db.add(sighting)
    await db.flush()
    await db.refresh(sighting)
    return sighting


async def get_sighting_by_id(db: AsyncSession, sighting_id: UUID) -> Optional[Sighting]:
    """Get a single sighting."""
    result = await db.execute(
        select(Sighting)
        .options(selectinload(Sighting.person))
        .where(Sighting.id == sighting_id)
    )
    sighting = result.scalar_one_or_none()
    if sighting:
        sighting.person_name = sighting.person.full_name if sighting.person else None
    return sighting


async def list_sightings_for_person(
    db: AsyncSession, person_id: UUID
) -> List[Sighting]:
    """All sightings for a missing person, ordered by detected_at DESC."""
    result = await db.execute(
        select(Sighting)
        .where(Sighting.person_id == person_id)
        .order_by(Sighting.detected_at.desc())
    )
    return list(result.scalars().all())


async def list_all_sightings(
    db: AsyncSession, limit: int = 50, status_filter: Optional[str] = None
) -> List[Sighting]:
    """List recent sightings across all missing persons."""
    stmt = select(Sighting).options(selectinload(Sighting.person))
    if status_filter:
        stmt = stmt.where(Sighting.status == status_filter)
    result = await db.execute(stmt.order_by(Sighting.detected_at.desc()).limit(limit))
    sightings = list(result.scalars().all())
    for s in sightings:
        s.person_name = s.person.full_name if s.person else None
    return sightings


async def confirm_sighting(
    db: AsyncSession, sighting_id: UUID, reviewer_id: UUID, notes: Optional[str] = None
) -> Optional[Sighting]:
    """Operator confirms a sighting. Triggers notification to reporter and closes active search."""
    sighting = await get_sighting_by_id(db, sighting_id)
    if not sighting:
        return None
    now = datetime.now(timezone.utc)
    sighting.status = "CONFIRMED"
    sighting.confidence_level = "CONFIRMED"
    sighting.reviewed_by = reviewer_id
    sighting.reviewed_at = now
    sighting.review_notes = notes

    # Close active search for the missing person upon confirmed match
    if sighting.person_id:
        if sighting.person:
            sighting.person.status = "FOUND"
            sighting.person.updated_at = now
        else:
            await db.execute(
                update(MissingPerson)
                .where(MissingPerson.id == sighting.person_id)
                .values(status="FOUND", updated_at=now)
            )
        # Deactivate face embeddings so Edge Agent prunes vector from FAISS surveillance
        await deactivate_embeddings_for_person(db, sighting.person_id)

    await db.flush()
    return sighting


async def reject_sighting(
    db: AsyncSession, sighting_id: UUID, reviewer_id: UUID, notes: Optional[str] = None
) -> Optional[Sighting]:
    """Operator rejects a false positive."""
    sighting = await get_sighting_by_id(db, sighting_id)
    if not sighting:
        return None
    sighting.status = "REJECTED"
    sighting.confidence_level = "REJECTED"
    sighting.reviewed_by = reviewer_id
    sighting.reviewed_at = datetime.now(timezone.utc)
    sighting.review_notes = notes
    await db.flush()
    return sighting


async def get_person_timeline(
    db: AsyncSession, person_id: UUID
) -> List[dict]:
    """
    Returns chronological list of sightings across cameras.
    The "last seen" feature.
    """
    result = await db.execute(
        select(
            Sighting.id,
            Sighting.detected_at,
            Sighting.similarity_score,
            Sighting.status,
            Sighting.camera_location,
            Sighting.latitude,
            Sighting.longitude,
            Camera.name.label("camera_name"),
        )
        .join(Camera, Sighting.camera_id == Camera.id)
        .where(Sighting.person_id == person_id)
        .where(Sighting.status != "REJECTED")
        .order_by(Sighting.detected_at.asc())
    )
    rows = result.all()
    return [
        {
            "sighting_id": str(row.id),
            "camera_name": row.camera_name,
            "camera_location": row.camera_location,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "detected_at": row.detected_at,
            "similarity_score": row.similarity_score,
            "status": row.status,
        }
        for row in rows
    ]
