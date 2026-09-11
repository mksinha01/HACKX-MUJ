"""API Routers package."""
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.agents import router as agents_router
from app.api.cameras import router as cameras_router
from app.api.reports import router as reports_router
from app.api.sightings import router as sightings_router
from app.api.embeddings import router as embeddings_router
from app.api.notifications import router as notifications_router
from app.api.sse import router as sse_router
from app.api.fir_verification import router as fir_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(agents_router)
api_router.include_router(cameras_router)
api_router.include_router(reports_router)
api_router.include_router(sightings_router)
api_router.include_router(embeddings_router)
api_router.include_router(notifications_router)
api_router.include_router(sse_router)
api_router.include_router(fir_router)

__all__ = [
    "api_router",
    "auth_router",
    "users_router",
    "agents_router",
    "cameras_router",
    "reports_router",
    "sightings_router",
    "embeddings_router",
    "notifications_router",
    "sse_router",
    "fir_router",
]
