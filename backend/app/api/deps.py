"""API dependencies: Database sessions, Auth, and Security guards."""
import hashlib
import logging
import os
import sys
from typing import AsyncGenerator, Optional
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, get_db
from app.models.edge_agent import EdgeAgent
from app.models.user import User

# Optional firebase_admin import
try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


def _hash_api_key(api_key: str) -> str:
    """Computes SHA-256 hash of API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def verify_enrollment_key(
    x_enrollment_key: Optional[str] = Header(None, alias="X-Enrollment-Key")
) -> str:
    """
    Validates Edge Agent device enrollment key.
    Required for POST /api/agents/register.
    """
    if not x_enrollment_key or x_enrollment_key != settings.ADMIN_ENROLLMENT_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid enrollment key",
        )
    return x_enrollment_key


async def verify_agent_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> EdgeAgent:
    """
    Validates incoming Edge Agent API key.
    Hashes the key with SHA-256 and searches the edge_agents table.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    key_hash = _hash_api_key(x_api_key)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.api_key_hash == key_hash)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Edge Agent API key",
        )

    return agent


def _verify_firebase_token_jwks(token: str) -> Optional[dict]:
    """Verifies Firebase Auth JWT against Google's public JWKS certificates."""
    try:
        import jwt
        from jwt import PyJWKClient
        jwks_url = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
        jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        project_id = settings.FIREBASE_PROJECT_ID
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
        )
        return decoded
    except Exception as e:
        logger.warning(f"JWKS Firebase token verification failed: {e}")
        return None


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    x_firebase_token: Optional[str] = Header(None, alias="X-Firebase-Token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates Firebase Auth JWT token and returns the corresponding User ORM record.
    Supports Authorization: Bearer <token> or X-Firebase-Token header.
    In testing/development, supports mock token bypass.
    """
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials
    elif x_firebase_token:
        token = x_firebase_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: missing Bearer token or X-Firebase-Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    firebase_uid: str = ""
    email: Optional[str] = None
    name: str = "User"

    # Support testing / mock tokens (in DEBUG or pytest/test mode)
    if token.startswith("test-") or token.startswith("mock-"):
        is_dev_or_test = (
            settings.DEBUG
            or "pytest" in sys.modules
            or os.environ.get("PYTEST_CURRENT_TEST") is not None
            or os.environ.get("TESTING", "").lower() in ("true", "1")
        )
        if not is_dev_or_test:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Test/mock tokens are not accepted in production mode",
                headers={"WWW-Authenticate": "Bearer"},
            )
        firebase_uid = f"uid_{token}"
        email = f"{token}@example.com"
        name = f"Test {token}"
    else:
        decoded_token = None
        if FIREBASE_AVAILABLE and len(getattr(firebase_admin, "_apps", {})) > 0:
            try:
                decoded_token = firebase_auth.verify_id_token(token)
            except Exception as e:
                logger.debug(f"firebase_auth.verify_id_token failed: {e}. Falling back to JWKS.")

        if not decoded_token:
            decoded_token = _verify_firebase_token_jwks(token)

        if decoded_token:
            firebase_uid = decoded_token.get("uid") or decoded_token.get("sub", "")
            email = decoded_token.get("email")
            name = decoded_token.get("name") or email or "User"
        elif settings.DEBUG:
            logger.warning("Unverified token accepted under DEBUG mode fallback.")
            firebase_uid = f"dev_uid_{hashlib.md5(token.encode()).hexdigest()[:16]}"
            email = f"{firebase_uid}@dev.local"
            name = "Dev User"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Firebase ID token: verification failed against Firebase and Google JWKS",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not resolve user identity from token",
        )

    # Lookup user in DB
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision user on first authenticated request
        user = User(
            id=uuid4(),
            firebase_uid=firebase_uid,
            name=name,
            email=email,
            language="en",
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user
