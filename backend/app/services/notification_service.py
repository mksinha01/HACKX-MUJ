"""Notification dispatcher service integrating Database Logging, SSE, and FCM Push."""
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import firebase_admin
    from firebase_admin import messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    firebase_admin = None  # type: ignore
    messaging = None  # type: ignore
    FIREBASE_AVAILABLE = False

from app.crud.notification import create_notification
from app.crud.user import get_user_by_id
from app.models.notification import Notification
from app.services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


async def dispatch_sighting_alert(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    body: str,
    sighting_id: UUID,
    data: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    Dispatches a sighting alert across three channels:
    1. Database notification record (durable log).
    2. Real-time Server-Sent Events (SSE) broadcast to the user's active session.
    3. Firebase Cloud Messaging (FCM) push notification (mobile app background alert).

    Gracefully falls back if FCM is unavailable or user has no registered FCM token.
    """
    payload_data = data or {}

    # 1. Log notification in database
    notif = await create_notification(
        db=db,
        user_id=user_id,
        type="SIGHTING",
        title=title,
        body=body,
        data=payload_data,
        sighting_id=sighting_id,
    )

    # 2. Broadcast to real-time SSE stream (User personal stream and Command Dashboard)
    sse_payload = {
        "event": "sighting",
        "notification_id": str(notif.id),
        "sighting_id": str(sighting_id),
        "title": title,
        "body": body,
        **payload_data,
    }
    await sse_manager.publish(f"user_{user_id}", sse_payload)
    await sse_manager.publish("dashboard_sightings", sse_payload)

    # 3. Dispatch FCM Push Notification if configured
    user = await get_user_by_id(db, user_id)
    if user and user.fcm_token and FIREBASE_AVAILABLE:
        try:
            # FCM data values must be strings
            fcm_data = {
                "sighting_id": str(sighting_id),
                "notification_id": str(notif.id),
                "type": "SIGHTING",
                **{k: str(v) for k, v in payload_data.items()},
            }
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=fcm_data,
                token=user.fcm_token,
            )
            response = messaging.send(message)
            logger.info(f"FCM alert sent successfully to user {user_id}: {response}")
        except Exception as e:
            logger.warning(f"Failed to dispatch FCM notification to user {user_id}: {e}")
    else:
        logger.debug(
            f"FCM push skipped for user {user_id} (FCM available: {FIREBASE_AVAILABLE}, token present: {bool(user and user.fcm_token)})"
        )

    return notif


async def send_sighting_notification(
    db: AsyncSession,
    user_id: UUID,
    sighting: Any,
) -> Notification:
    """
    Convenience method to construct and dispatch a standardized sighting alert.
    """
    score = getattr(sighting, "similarity_score", 0.0) or 0.0
    title = "Sighting Alert / सूचना अलर्ट"
    body = (
        f"A possible match ({score * 100:.1f}%) was detected for your report. "
        "Tap to review evidence."
    )
    sighting_id = getattr(sighting, "id", None)

    metadata = {
        "similarity_score": score,
        "camera_id": str(getattr(sighting, "camera_id", "") or ""),
        "person_id": str(getattr(sighting, "person_id", "") or ""),
    }

    return await dispatch_sighting_alert(
        db=db,
        user_id=user_id,
        title=title,
        body=body,
        sighting_id=sighting_id,
        data=metadata,
    )
