"""FIND-MISSING-PEP Backend Application Entrypoint."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import settings
from app.database import close_db, init_db

logger = logging.getLogger(__name__)


def ensure_upload_directories():
    """Ensure upload media directories exist on disk."""
    base_dir = Path(settings.UPLOAD_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "photos").mkdir(parents=True, exist_ok=True)
    (base_dir / "faces").mkdir(parents=True, exist_ok=True)
    (base_dir / "evidence").mkdir(parents=True, exist_ok=True)


def init_firebase():
    """Initialize Firebase Admin SDK if service account is present."""
    try:
        import firebase_admin
        from firebase_admin import credentials
        if not getattr(firebase_admin, "_apps", None):
            sa_path = Path(settings.FIREBASE_CREDENTIALS_PATH)
            if sa_path.exists():
                cred = credentials.Certificate(str(sa_path))
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin initialized with service account.")
            else:
                logger.info(
                    f"Firebase service account not found at {sa_path}; "
                    f"Google JWKS public certificate verification active for project '{settings.FIREBASE_PROJECT_ID}'."
                )
    except Exception as e:
        logger.warning(f"Firebase Admin initialization skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and graceful shutdown."""
    logger.info("Initializing FIND-MISSING-PEP Backend Services...")

    # Security: validate secrets configuration
    security_warnings = settings.validate_secrets_for_production()
    for warning in security_warnings:
        if settings.is_production:
            logger.error(f"🚫 SECURITY BLOCK: {warning}")
        else:
            logger.warning(f"⚠️  SECURITY WARNING: {warning}")
    
    if settings.is_production and security_warnings:
        raise RuntimeError(
            "Cannot start in production mode with insecure configuration. "
            "Fix the warnings above before deploying."
        )

    ensure_upload_directories()
    init_firebase()
    await init_db()

    # Preload and warm up AI face recognition models asynchronously
    import asyncio
    from app.services.face_processing import warmup_face_models
    asyncio.create_task(asyncio.to_thread(warmup_face_models))

    yield
    logger.info("Shutting down FIND-MISSING-PEP Backend Services...")
    await close_db()


def create_app() -> FastAPI:
    """FastAPI application factory."""
    ensure_upload_directories()

    application = FastAPI(
        title="FIND-MISSING-PEP Backend API",
        description="AI-Based Missing Person Detection & Real-Time CCTV Monitoring System",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 1. CORS Middleware — explicit origins, methods, and headers for security
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Firebase-Token",
            "X-API-Key",
            "X-Enrollment-Key",
        ],
    )

    # 2. Static File Mount for uploaded media
    application.mount(
        "/uploads",
        StaticFiles(directory=settings.UPLOAD_DIR),
        name="uploads",
    )

    # 3. Static File Mount for Web App Interface
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    # 4. Web App Entrypoint routes
    from fastapi.responses import FileResponse

    @application.get("/", response_class=FileResponse, tags=["web-app"])
    @application.get("/app", response_class=FileResponse, tags=["web-app"])
    async def serve_web_app():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {
            "status": "ok",
            "version": "1.0.0",
            "service": "FIND-MISSING-PEP Backend",
            "docs": "/docs",
        }

    # 5. Health Check endpoint (No Auth)
    @application.get("/health", tags=["health"])
    async def health_check():
        return {
            "status": "ok",
            "version": "1.0.0",
            "service": "FIND-MISSING-PEP Backend",
        }

    # 6. Include REST API Routers
    application.include_router(api_router)

    # 7. Direct SSE stream mount (/events/stream alias for EventSource clients)
    from app.api.sse import router as sse_router
    application.include_router(sse_router)

    return application


app = create_app()
