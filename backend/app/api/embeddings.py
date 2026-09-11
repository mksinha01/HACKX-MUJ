"""Embeddings synchronization endpoint for Edge Agents."""
import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_agent_api_key
from app.models.edge_agent import EdgeAgent
from app.schemas.face_embedding import EmbeddingPersonItem, EmbeddingSyncResponse
from app.services.embedding_sync import get_sync_package

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.get("/sync", response_model=EmbeddingSyncResponse)
async def sync_embeddings(
    since: Optional[str] = Query(
        None,
        description="ISO 8601 timestamp for incremental sync; omit for full sync",
    ),
    agent: EdgeAgent = Depends(verify_agent_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronizes ArcFace 512-D face embeddings to Edge Agents.
    If 'since' is omitted, returns all active embeddings (full sync).
    If 'since' is provided, returns active embeddings updated since that timestamp,
    along with 'removed_ids' (tombstones) for reports that were resolved, closed, or deactivated.
    Embedding vectors are base64-encoded bytes for fast, reliable JSON transmission.
    """
    parsed_since: Optional[datetime] = None
    if since:
        clean_since = since.strip().replace(" ", "+")
        try:
            parsed_since = datetime.fromisoformat(clean_since)
        except Exception:
            try:
                parsed_since = datetime.strptime(clean_since, "%Y-%m-%dT%H:%M:%S.%f")
            except Exception:
                pass

    package = await get_sync_package(db, parsed_since)

    # Encode raw byte vectors to base64 strings for clean JSON transport
    encoded_persons = []
    for item in package.get("persons", []):
        raw_bytes = item.get("embedding_bytes")
        if isinstance(raw_bytes, bytes):
            b64_str = base64.b64encode(raw_bytes).decode("ascii")
        elif isinstance(raw_bytes, str):
            b64_str = raw_bytes
        else:
            b64_str = ""

        encoded_persons.append(
            EmbeddingPersonItem(
                embedding_id=str(item.get("embedding_id", "")),
                person_id=str(item.get("person_id", "")),
                person_name=str(item.get("person_name", "")),
                embedding_bytes=b64_str,
                quality_score=item.get("quality_score"),
                created_at=item.get("created_at"),
                photo_url=item.get("photo_url"),
                age=item.get("age"),
                gender=item.get("gender"),
                height_cm=item.get("height_cm"),
                description=item.get("description"),
                last_seen_location=item.get("last_seen_location"),
                last_seen_time=item.get("last_seen_time"),
                contact_info=item.get("contact_info"),
                reporter_name=item.get("reporter_name"),
                reporter_email=item.get("reporter_email"),
                reporter_phone=item.get("reporter_phone"),
            )
        )

    # Update agent's last sync timestamp
    agent.last_sync_at = datetime.now(timezone.utc)
    await db.flush()

    return EmbeddingSyncResponse(
        full_sync=package.get("full_sync", False),
        persons=encoded_persons,
        removed_ids=package.get("removed_ids", []),
        sync_timestamp=package.get("sync_timestamp", datetime.now(timezone.utc).isoformat()),
    )
