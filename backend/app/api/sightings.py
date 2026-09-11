"""Sighting ingestion, verification, and review endpoints."""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_api_key
from app.config import settings
from app.crud.sighting import (
    confirm_sighting,
    get_sighting_by_id,
    list_all_sightings,
    reject_sighting,
)
from app.models.edge_agent import EdgeAgent
from app.models.missing_person import MissingPerson
from app.models.sighting import Sighting
from app.models.user import User
from app.schemas.sighting import SightingResponse, SightingReview
from app.services.notification_service import dispatch_sighting_alert
from app.services.sse_manager import sse_manager
from app.utils.file_storage import save_upload_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sightings", tags=["sightings"])


@router.get("/", response_model=list[SightingResponse])
async def list_recent_sightings(
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List recent sightings across all cameras for dashboard monitoring."""
    return await list_all_sightings(db, limit=limit, status_filter=status_filter)


@router.post(
    "/",
    response_model=SightingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_sighting(
    person_id: UUID = Form(...),
    camera_id: UUID = Form(...),
    similarity_score: float = Form(...),
    detected_at: datetime = Form(...),
    confidence_level: str = Form("POSSIBLE"),
    num_frames_matched: Optional[int] = Form(None),
    camera_location: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    face_crop: UploadFile = File(..., description="Cropped face image (112x112)"),
    full_frame: UploadFile = File(..., description="Full CCTV scene capture"),
    video_clip: Optional[UploadFile] = File(None, description="Pre/post temporal video clip"),
    agent: EdgeAgent = Depends(verify_agent_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a sighting event reported by an Edge Agent.
    Saves evidence files (face crop, full frame, optional video clip),
    creates a Sighting record, and dispatches FCM/SSE notifications to the report owner.
    """
    # 1. Save evidence media files
    face_crop_path = await save_upload_file(
        file=face_crop,
        subfolder="evidence",
        upload_dir=settings.UPLOAD_DIR,
    )
    full_frame_path = await save_upload_file(
        file=full_frame,
        subfolder="evidence",
        upload_dir=settings.UPLOAD_DIR,
    )
    video_clip_path = None
    if video_clip and video_clip.filename:
        video_clip_path = await save_upload_file(
            file=video_clip,
            subfolder="evidence",
            upload_dir=settings.UPLOAD_DIR,
        )

    # 2. Create Sighting record
    sighting = Sighting(
        id=uuid4(),
        person_id=person_id,
        agent_id=agent.id,
        camera_id=camera_id,
        similarity_score=similarity_score,
        confidence_level=confidence_level,
        num_frames_matched=num_frames_matched,
        camera_location=camera_location,
        latitude=latitude,
        longitude=longitude,
        detected_at=detected_at,
        face_crop_path=face_crop_path,
        full_frame_path=full_frame_path,
        video_clip_path=video_clip_path,
        status="PENDING",
    )
    db.add(sighting)
    await db.flush()
    await db.refresh(sighting)

    # 3. Lookup person to notify the creator/family and broadcast to dashboard
    result = await db.execute(
        select(MissingPerson).where(MissingPerson.id == person_id)
    )
    person = result.scalar_one_or_none()

    person_name = person.full_name if person else "Unknown Person"
    pct = int(similarity_score * 100)
    title = f"Possible Match Detected: {person_name} ({pct}%)"
    body = (
        f"A possible match was spotted on camera {camera_location or 'CCTV'} "
        f"at {detected_at.strftime('%H:%M:%S')}."
    )

    sighting_data = {
        "sighting_id": str(sighting.id),
        "person_id": str(person_id),
        "person_name": person_name,
        "similarity": float(similarity_score),
        "camera_id": str(camera_id),
        "camera_location": camera_location or "CCTV Surveillance Camera",
        "confidence_level": confidence_level,
        "face_crop_path": face_crop_path,
        "full_frame_path": full_frame_path,
        "video_clip_path": video_clip_path,
        "detected_at": detected_at.isoformat() if hasattr(detected_at, "isoformat") else str(detected_at),
        "latitude": latitude,
        "longitude": longitude,
        "num_frames_matched": num_frames_matched,
    }

    if person:
        try:
            await dispatch_sighting_alert(
                db=db,
                user_id=person.user_id,
                title=title,
                body=body,
                sighting_id=sighting.id,
                data=sighting_data,
            )
        except Exception as ne:
            logger.error(f"Failed to dispatch sighting alert: {ne}")
    else:
        try:
            sse_payload = {
                "event": "sighting",
                "title": title,
                "body": body,
                **sighting_data,
            }
            await sse_manager.publish("dashboard_sightings", sse_payload)
        except Exception as se:
            logger.error(f"Failed to broadcast sighting to dashboard: {se}")

    return sighting


@router.get("/{sighting_id}", response_model=SightingResponse)
async def get_sighting_detail(
    sighting_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details and evidence paths for a specific sighting."""
    sighting = await get_sighting_by_id(db, sighting_id)
    if not sighting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sighting not found",
        )
    return sighting


@router.put("/{sighting_id}/confirm", response_model=SightingResponse)
async def confirm_sighting_match(
    sighting_id: UUID,
    review: Optional[SightingReview] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a sighting match (operator review action)."""
    notes = review.review_notes if review else None
    confirmed = await confirm_sighting(
        db=db,
        sighting_id=sighting_id,
        reviewer_id=current_user.id,
        notes=notes,
    )
    if not confirmed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sighting not found",
        )
    return confirmed


@router.put("/{sighting_id}/reject", response_model=SightingResponse)
async def reject_sighting_match(
    sighting_id: UUID,
    review: Optional[SightingReview] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a false positive sighting (operator review action)."""
    notes = review.review_notes if review else None
    rejected = await reject_sighting(
        db=db,
        sighting_id=sighting_id,
        reviewer_id=current_user.id,
        notes=notes,
    )
    if not rejected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sighting not found",
        )
    return rejected
