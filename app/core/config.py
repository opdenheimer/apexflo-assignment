from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "ApexFlo In-Cinema Commerce"
    APP_ENV: str = "development"
    PORT: int = 8000
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://apexflo:apexflo_secret@localhost:5432/apexflo_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Stateless Tokens / Security
    SECRET_KEY: str = "apexflo_production_secret_key_cinema_2026_super_secure"
    ALGORITHM: str = "HS256"
    PATRON_SESSION_COOKIE_NAME: str = "apexflo_patron_session"
    ADMIN_SESSION_COOKIE_NAME: str = "apexflo_admin_session"
    SESSION_TTL_HOURS: int = 12
    ADMIN_ACCESS_KEY: str = "apexflo-admin-demo"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
