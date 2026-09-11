from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent

class Settings(BaseSettings):
    APP_ENV: str = "development"  # development | staging | production
    
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
    
    # Upload security
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_UPLOAD_EXTENSIONS: str = ".jpg,.jpeg,.png,.webp,.mp4,.pdf"
    
    DEBUG: bool = True
    DATABASE_URL: str | None = None
    DATABASE_URL_OVERRIDE: str | None = None
    
    _DEFAULT_SECRETS = {
        "dev-enroll-secret-change-me",
        "32bytehexsecretforaesencryption00",
    }
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "staging")
    
    def validate_secrets_for_production(self) -> list[str]:
        """Returns list of warning messages for insecure configuration."""
        warnings = []
        if self.ADMIN_ENROLLMENT_KEY in self._DEFAULT_SECRETS:
            warnings.append(
                "ADMIN_ENROLLMENT_KEY is set to the default value! "
                "Generate a secure key: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if self.RTSP_SECRET_KEY in self._DEFAULT_SECRETS:
            warnings.append(
                "RTSP_SECRET_KEY is set to the default value! "
                "Generate a secure key: python -c \"import secrets; print(secrets.token_hex(16))\""
            )
        if self.is_production and self.DEBUG:
            warnings.append("DEBUG=True is active in production mode! Set DEBUG=false.")
        return warnings

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

