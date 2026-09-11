"""CRUD operations for face_embeddings table."""
from datetime import datetime, timezone
from typing import List, Optional, Set
from uuid import UUID
import numpy as np
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face_embedding import FaceEmbedding
from app.models.missing_person import MissingPerson
from app.models.photo import Photo
from app.models.user import User


async def store_embedding(
    db: AsyncSession,
    person_id: UUID,
    photo_id: UUID,
    embedding: np.ndarray,
    quality_score: float,
) -> FaceEmbedding:
    """
    Store a 512-D face embedding vector as binary bytes.
    Ensures float32 and L2-normalized format.
    """
    embedding_bytes = embedding.astype(np.float32).tobytes()
    record = FaceEmbedding(
        person_id=person_id,
        photo_id=photo_id,
        embedding=embedding_bytes,
        quality_score=quality_score,
        is_active=True,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_active_embeddings(db: AsyncSession) -> List[dict]:
    """
    Returns all embeddings for ACTIVE missing persons with is_active=True.
    Used by Edge Agents during full synchronization.
    """
    result = await db.execute(
        select(
            FaceEmbedding.id,
            FaceEmbedding.person_id,
            FaceEmbedding.embedding,
            FaceEmbedding.quality_score,
            FaceEmbedding.created_at,
            MissingPerson.full_name,
            MissingPerson.age,
            MissingPerson.gender,
            MissingPerson.height_cm,
            MissingPerson.description,
            MissingPerson.last_seen_location,
            MissingPerson.last_seen_time,
            MissingPerson.contact_info,
            Photo.face_crop_path,
            Photo.original_path,
            User.name.label("reporter_name"),
            User.email.label("reporter_email"),
            User.phone.label("reporter_phone"),
        )
        .join(MissingPerson, FaceEmbedding.person_id == MissingPerson.id)
        .outerjoin(Photo, FaceEmbedding.photo_id == Photo.id)
        .outerjoin(User, MissingPerson.user_id == User.id)
        .where(MissingPerson.status == "ACTIVE")
        .where(FaceEmbedding.is_active == True)  # noqa: E712
    )
    rows = result.all()
    return [
        {
            "embedding_id": str(row.id),
            "person_id": str(row.person_id),
            "person_name": row.full_name,
            "embedding_bytes": row.embedding,
            "quality_score": row.quality_score,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "photo_url": row.face_crop_path or row.original_path,
            "age": row.age,
            "gender": row.gender,
            "height_cm": row.height_cm,
            "description": row.description,
            "last_seen_location": row.last_seen_location,
            "last_seen_time": row.last_seen_time.isoformat() if row.last_seen_time else None,
            "contact_info": row.contact_info,
            "reporter_name": row.reporter_name,
            "reporter_email": row.reporter_email,
            "reporter_phone": row.reporter_phone,
        }
        for row in rows
    ]


async def get_embeddings_since(
    db: AsyncSession, since: datetime
) -> List[dict]:
    """
    Returns active embeddings created or updated since a given timestamp.
    Used for incremental synchronization by Edge Agents.
    """
    result = await db.execute(
        select(
            FaceEmbedding.id,
            FaceEmbedding.person_id,
            FaceEmbedding.embedding,
            FaceEmbedding.quality_score,
            FaceEmbedding.created_at,
            MissingPerson.full_name,
            MissingPerson.age,
            MissingPerson.gender,
            MissingPerson.height_cm,
            MissingPerson.description,
            MissingPerson.last_seen_location,
            MissingPerson.last_seen_time,
            MissingPerson.contact_info,
            Photo.face_crop_path,
            Photo.original_path,
            User.name.label("reporter_name"),
            User.email.label("reporter_email"),
            User.phone.label("reporter_phone"),
        )
        .join(MissingPerson, FaceEmbedding.person_id == MissingPerson.id)
        .outerjoin(Photo, FaceEmbedding.photo_id == Photo.id)
        .outerjoin(User, MissingPerson.user_id == User.id)
        .where(MissingPerson.status == "ACTIVE")
        .where(FaceEmbedding.is_active == True)  # noqa: E712
        .where(
            or_(
                FaceEmbedding.updated_at >= since,
                FaceEmbedding.created_at >= since,
                MissingPerson.updated_at >= since,
            )
        )
    )
    rows = result.all()
    return [
        {
            "embedding_id": str(row.id),
            "person_id": str(row.person_id),
            "person_name": row.full_name,
            "embedding_bytes": row.embedding,
            "quality_score": row.quality_score,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "photo_url": row.face_crop_path or row.original_path,
            "age": row.age,
            "gender": row.gender,
            "height_cm": row.height_cm,
            "description": row.description,
            "last_seen_location": row.last_seen_location,
            "last_seen_time": row.last_seen_time.isoformat() if row.last_seen_time else None,
            "contact_info": row.contact_info,
            "reporter_name": row.reporter_name,
            "reporter_email": row.reporter_email,
            "reporter_phone": row.reporter_phone,
        }
        for row in rows
    ]


async def get_deactivated_person_ids_since(
    db: AsyncSession, since: datetime
) -> List[str]:
    """
    Computes person IDs whose status transitioned to FOUND/CLOSED, or whose embeddings
    were deactivated since the timestamp (tombstones for Edge Agents).
    """
    # 1. Reports updated to non-ACTIVE (FOUND or CLOSED)
    result_reports = await db.execute(
        select(MissingPerson.id)
        .where(MissingPerson.updated_at >= since)
        .where(MissingPerson.status.in_(["FOUND", "CLOSED"]))
    )
    found_closed_ids: Set[str] = {str(pid) for pid in result_reports.scalars().all()}

    # 2. Inactive embeddings updated since timestamp
    result_embeddings = await db.execute(
        select(FaceEmbedding.person_id)
        .where(FaceEmbedding.updated_at >= since)
        .where(FaceEmbedding.is_active == False)  # noqa: E712
    )
    deactivated_emb_ids: Set[str] = {str(pid) for pid in result_embeddings.scalars().all()}

    return list(found_closed_ids.union(deactivated_emb_ids))


async def get_embeddings_for_person(
    db: AsyncSession, person_id: UUID
) -> List[FaceEmbedding]:
    """Get all embeddings for a specific missing person."""
    result = await db.execute(
        select(FaceEmbedding)
        .where(FaceEmbedding.person_id == person_id)
        .order_by(FaceEmbedding.quality_score.desc())
    )
    return list(result.scalars().all())


async def deactivate_embeddings_for_person(
    db: AsyncSession, person_id: UUID
) -> int:
    """Mark all embeddings for a person as inactive (e.g. when report is resolved)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(FaceEmbedding)
        .where(FaceEmbedding.person_id == person_id)
        .values(is_active=False, updated_at=now)
    )
    await db.flush()
    return result.rowcount
