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
from app.models.camera import Camera
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent sightings across all cameras for dashboard monitoring. Requires authentication."""
    return await list_all_sightings(db, limit=limit, status_filter=status_filter)


@router.post(
    "/",
    response_model=SightingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_sighting(
    person_id: str = Form(..., description="UUID of the missing person"),
    camera_id: str = Form(..., description="Camera UUID or local identifier e.g. CAM-01"),
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
    # 0. Validate and resolve person_id
    try:
        resolved_person_id = UUID(str(person_id).strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid person_id: '{person_id}' is not a valid UUID",
        )

    # 0b. Resolve camera_id (supports backend UUID or local identifier like 'CAM-01')
    resolved_camera_id: Optional[UUID] = None
    clean_cam_str = str(camera_id).strip()
    try:
        parsed_cam_uuid = UUID(clean_cam_str)
        cam_res = await db.execute(
            select(Camera).where(Camera.id == parsed_cam_uuid)
        )
        if cam_res.scalar_one_or_none():
            resolved_camera_id = parsed_cam_uuid
    except (ValueError, TypeError, AttributeError):
        pass

    if not resolved_camera_id:
        # Search by local_camera_id for this agent
        cam_res = await db.execute(
            select(Camera).where(
                Camera.agent_id == agent.id,
                Camera.local_camera_id == clean_cam_str,
            )
        )
        cam = cam_res.scalar_one_or_none()
        if cam:
            resolved_camera_id = cam.id

    if not resolved_camera_id:
        # Fallback to any registered camera for this agent
        cam_res = await db.execute(
            select(Camera).where(Camera.agent_id == agent.id).limit(1)
        )
        cam = cam_res.scalar_one_or_none()
        if cam:
            resolved_camera_id = cam.id

    if not resolved_camera_id:
        # Auto-provision camera if none exists for agent
        new_cam = Camera(
            id=uuid4(),
            agent_id=agent.id,
            name=camera_location or f"Camera {clean_cam_str}",
            local_camera_id=clean_cam_str[:50],
            encrypted_rtsp_url="local://auto-provisioned",
            location=camera_location or "Surveillance Zone",
            status="ACTIVE",
        )
        db.add(new_cam)
        await db.flush()
        resolved_camera_id = new_cam.id

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
        person_id=resolved_person_id,
        agent_id=agent.id,
        camera_id=resolved_camera_id,
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
        select(MissingPerson).where(MissingPerson.id == resolved_person_id)
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
        "person_id": str(resolved_person_id),
        "person_name": person_name,
        "similarity": float(similarity_score),
        "camera_id": str(resolved_camera_id),
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

    sighting.person_name = person_name
    return sighting


@router.get("/{sighting_id}", response_model=SightingResponse)
async def get_sighting_detail(
    sighting_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details and evidence paths for a specific sighting. Requires authentication."""
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
    """Confirm a sighting match (operator review action) and close active search."""
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

    # Dispatch resolution notification and SSE broadcast informing that active search is closed
    person = confirmed.person
    if not person and confirmed.person_id:
        p_res = await db.execute(select(MissingPerson).where(MissingPerson.id == confirmed.person_id))
        person = p_res.scalar_one_or_none()

    if person:
        title = f"Case Resolved: {person.full_name} Found"
        body = (
            f"Verified CCTV match confirmed on camera {confirmed.camera_location or 'CCTV'}. "
            f"Active search has been closed."
        )
        try:
            await dispatch_sighting_alert(
                db=db,
                user_id=person.user_id,
                title=title,
                body=body,
                sighting_id=confirmed.id,
                data={
                    "event_type": "CASE_RESOLVED",
                    "status": "FOUND",
                    "person_id": str(person.id),
                    "person_name": person.full_name,
                    "camera_location": confirmed.camera_location or "CCTV",
                    "similarity": float(confirmed.similarity_score or 0.0),
                    "confidence_level": "CONFIRMED",
                },
                notif_type="CONFIRMATION",
            )
        except Exception as ne:
            logger.error(f"Failed to dispatch case resolution alert: {ne}")
    else:
        try:
            sse_payload = {
                "event": "sighting",
                "type": "CONFIRMATION",
                "sighting_id": str(confirmed.id),
                "title": "Match Confirmed",
                "body": f"Sighting {confirmed.id} confirmed. Active search closed.",
                "status": "CONFIRMED",
            }
            await sse_manager.publish("dashboard_sightings", sse_payload)
        except Exception as se:
            logger.error(f"Failed to broadcast match confirmation to dashboard: {se}")

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
