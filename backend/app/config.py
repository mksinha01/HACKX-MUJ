from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent

class Settings(BaseSettings):
    POSTGRES_USER: str = "fmp_user"
    POSTGRES_PASSWORD: str = "fmp_pass"
    POSTGRES_DB: str = "fmp_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
    ADMIN_ENROLLMENT_KEY: str = "dev-enroll-secret-change-me"
    RTSP_SECRET_KEY: str = "32bytehexsecretforaesencryption00"
    
    UPLOAD_DIR: str = str(_project_root / "uploads")
    FIREBASE_CREDENTIALS_PATH: str = str(_backend_dir / "firebase-sa.json")
    FIREBASE_PROJECT_ID: str = "find-missing-pep"
    AI_MODEL_DIR: str = str(_project_root / "ai_models")
    
    DEBUG: bool = True
    DATABASE_URL: str | None = None
    DATABASE_URL_OVERRIDE: str | None = None

    model_config = SettingsConfigDict(
        env_file=[".env", str(_backend_dir / ".env"), str(_project_root / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def DATABASE_URL_RESOLVED(self) -> str:
        return self.DATABASE_URL_ASYNC

settings = Settings()

