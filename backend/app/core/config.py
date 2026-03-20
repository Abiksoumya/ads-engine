"""
AdEngineAI — Core Configuration
==================================
All settings loaded from environment variables.
Never hardcode values — always use this config.

Usage anywhere:
    from app.core.config import settings
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── App ────────────────────────────────────────────────────────────
    APP_NAME: str = "AdEngineAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    FRONTEND_URL: str = "http://localhost:3000"

    # ─── Database ───────────────────────────────────────────────────────
    DATABASE_URL: str = ""                         # postgresql+asyncpg://...
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False                      # set True to log all SQL

    # ─── Redis ──────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ─── JWT ────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = ""                       # min 64 chars random string
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── Security ───────────────────────────────────────────────────────
    BCRYPT_ROUNDS: int = 12
    RATE_LIMIT_PER_MINUTE: int = 60           # default per user per endpoint
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10      # stricter for auth endpoints

    # ─── Stripe ─────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""            # price ID from Stripe dashboard
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_AGENCY: str = ""

    # ─── LLM ────────────────────────────────────────────────────────────
    LLM_ENV: Literal["development", "production"] = "development"
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # ─── Storage ────────────────────────────────────────────────────────
    STORAGE_ENV: Literal["development", "production"] = "development"
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "adengineai-videos"
    AWS_REGION: str = "us-east-1"

    # ─── Video ──────────────────────────────────────────────────────────
    VIDEO_ENV: Literal["development", "production", "mock"] = "mock"
    DID_API_KEY: str = ""
    HEYGEN_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    # ─── Social Platforms ───────────────────────────────────────────────
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = "http://localhost:8001/auth/youtube/callback"
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""

    # ─── Agent Sidecar ──────────────────────────────────────────────────
    SIDECAR_PORT: int = 8001

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def allowed_origins(self) -> list[str]:
        """CORS allowed origins based on environment."""
        if self.is_development:
            return [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",   # Vite default
            ]
        return [self.FRONTEND_URL]


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached settings instance.
    Use this everywhere instead of instantiating Settings() directly.
    """
    return Settings()


# Single shared instance
settings = get_settings()