"""Edge Agent registration, heartbeat, and camera sync endpoints."""
from typing import List, Union
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_agent_api_key, verify_enrollment_key, get_current_user
from app.config import settings
from app.crud.edge_agent import (
    get_agent_by_id,
    list_agents,
    register_agent,
    update_heartbeat,
)
from app.models.camera import Camera
from app.models.edge_agent import EdgeAgent
from app.schemas.camera import (
    CameraSyncItem,
    CameraSyncRequest,
    CameraSyncResponse,
)
from app.schemas.edge_agent import (
    AgentHeartbeat,
    AgentRegister,
    AgentRegisterResponse,
    AgentResponse,
)
from app.utils.crypto import AESGCMCrypto

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_edge_agent(
    data: AgentRegister,
    enrollment_key: str = Depends(verify_enrollment_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a newly installed Edge Agent device.
    Protected by X-Enrollment-Key header matching settings.ADMIN_ENROLLMENT_KEY.
    Generates a secure API key, stores SHA-256 hash, and returns plaintext key once.
    """
    agent, plain_api_key = await register_agent(db, data)
    return AgentRegisterResponse(
        agent_id=agent.id,
        api_key=plain_api_key,
        message="Agent registered successfully. Store API key safely; it cannot be recovered.",
    )


@router.post("/{agent_id}/heartbeat", response_model=AgentResponse)
async def agent_heartbeat(
    agent_id: UUID,
    payload: AgentHeartbeat,
    agent: EdgeAgent = Depends(verify_agent_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Heartbeat ping sent by Edge Agent every 30-60 seconds.
    Requires X-API-Key header.
    """
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not belong to specified agent ID",
        )

    updated = await update_heartbeat(
        db=db,
        agent_id=agent_id,
        status=payload.status,
        camera_count=payload.camera_count,
        version=payload.version,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return updated


@router.get("/", response_model=List[AgentResponse])
async def list_all_agents(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all registered edge agent devices. Requires authentication."""
    return await list_agents(db)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_detail(
    agent_id: UUID,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific edge agent. Requires authentication."""
    agent = await get_agent_by_id(db, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@router.post("/{agent_id}/cameras/sync", response_model=CameraSyncResponse)
async def sync_agent_cameras(
    agent_id: UUID,
    payload: Union[CameraSyncRequest, List[CameraSyncItem]],
    agent: EdgeAgent = Depends(verify_agent_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronizes an Edge Agent's local camera configurations.
    Accepts local camera identifiers (e.g. CAM-01), encrypts RTSP URLs at rest
    using AES-256-GCM, upserts into the database, and returns a mapping
    from local camera IDs to backend camera UUIDs.
    """
    if agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not match agent ID",
        )

    cameras_list: List[CameraSyncItem] = (
        payload.cameras if isinstance(payload, CameraSyncRequest) else payload
    )

    crypto = AESGCMCrypto(settings.RTSP_SECRET_KEY)
    mappings: dict[str, str] = {}

    for cam in cameras_list:
        encrypted_url = crypto.encrypt(cam.rtsp_url)

        # Check if this local camera already exists for this agent
        result = await db.execute(
            select(Camera).where(
                Camera.agent_id == agent_id,
                Camera.local_camera_id == cam.local_camera_id,
            )
        )
        existing_cam = result.scalar_one_or_none()

        if existing_cam:
            existing_cam.name = cam.name
            existing_cam.encrypted_rtsp_url = encrypted_url
            existing_cam.location = cam.location
            existing_cam.latitude = cam.latitude
            existing_cam.longitude = cam.longitude
            existing_cam.resolution = cam.resolution
            existing_cam.status = "ACTIVE"
            camera_record = existing_cam
        else:
            camera_record = Camera(
                id=uuid4(),
                agent_id=agent_id,
                local_camera_id=cam.local_camera_id,
                name=cam.name,
                encrypted_rtsp_url=encrypted_url,
                location=cam.location,
                latitude=cam.latitude,
                longitude=cam.longitude,
                resolution=cam.resolution,
                status="ACTIVE",
            )
            db.add(camera_record)

        await db.flush()
        mappings[cam.local_camera_id] = str(camera_record.id)

    # Update agent camera count
    agent.camera_count = len(mappings)
    await db.flush()

    return CameraSyncResponse(mappings=mappings)
