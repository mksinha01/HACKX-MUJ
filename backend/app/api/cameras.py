"""Camera management endpoints."""
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, verify_agent_api_key
from app.config import settings
from app.models.camera import Camera
from app.models.edge_agent import EdgeAgent
from app.schemas.camera import CameraCreate, CameraResponse
from app.utils.crypto import AESGCMCrypto

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def register_single_camera(
    data: CameraCreate,
    agent: EdgeAgent = Depends(verify_agent_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a camera channel for the calling Edge Agent.
    Encrypts the RTSP URL at rest using AES-256-GCM.
    """
    crypto = AESGCMCrypto(settings.RTSP_SECRET_KEY)
    encrypted_url = crypto.encrypt(data.rtsp_url)

    # Check for existing camera with same local_camera_id on this agent
    result = await db.execute(
        select(Camera).where(
            Camera.agent_id == agent.id,
            Camera.local_camera_id == data.local_camera_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.name = data.name
        existing.encrypted_rtsp_url = encrypted_url
        existing.location = data.location
        existing.latitude = data.latitude
        existing.longitude = data.longitude
        existing.resolution = data.resolution
        existing.status = "ACTIVE"
        cam = existing
    else:
        cam = Camera(
            id=uuid4(),
            agent_id=agent.id,
            local_camera_id=data.local_camera_id,
            name=data.name,
            encrypted_rtsp_url=encrypted_url,
            location=data.location,
            latitude=data.latitude,
            longitude=data.longitude,
            resolution=data.resolution,
            status="ACTIVE",
        )
        db.add(cam)

    await db.flush()
    await db.refresh(cam)
    return cam


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(
    agent_id: Optional[UUID] = Query(None, description="Filter by Edge Agent ID"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List cameras, optionally filtered by agent_id. Requires authentication."""
    stmt = select(Camera)
    if agent_id:
        stmt = stmt.where(Camera.agent_id == agent_id)
    stmt = stmt.order_by(Camera.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: UUID,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of a single camera. Requires authentication."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    return cam
