"""Server-Sent Events (SSE) stream endpoint for live foreground UI updates."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, security_bearer
from app.models.user import User
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def events_stream(
    request: Request,
    token: Optional[str] = Query(
        None,
        description="Firebase Auth token (query param supported for browser/Flutter EventSource)",
    ),
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events (SSE) stream for real-time mobile app and UI updates.
    Accepts token as Bearer header or '?token=...' query parameter.
    Yields 'event: sighting' and keep-alive ':ping' every 30 seconds.
    """
    effective_token = token or (auth_header.credentials if auth_header else None)

    if not effective_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth token for SSE stream",
        )

    # Resolve user
    user = await get_current_user(
        auth_header=HTTPAuthorizationCredentials(scheme="Bearer", credentials=effective_token),
        x_firebase_token=None,
        db=db,
    )

    channels = [f"user_{user.id}", "dashboard_sightings"]

    return StreamingResponse(
        sse_manager.event_generator(channel=channels, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
