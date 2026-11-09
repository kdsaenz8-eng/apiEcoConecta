"""
Configuración central de variables de entorno mediante Pydantic Settings v2.
Soporta configuración para PostgreSQL asíncrono, JWT y almacenamiento cloud de evidencias.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de configuración de infraestructura y seguridad."""

    PROJECT_NAME: str = "EcoConecta API - TRL 5"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Base de datos PostgreSQL 15+ con driver asíncrono asyncpg
    DATABASE_URL: str = (
        "postgresql+asyncpg://ecoconecta_user:ecoconecta_pass@db:5432/ecoconecta_db"
    )

    # Seguridad y Tokens JWT (OAuth2 Password Bearer)
    SECRET_KEY: str = "ecoconecta-ecoconecta-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas para operación en campo

    # Normativa Ley 1581 de 2012 (Habeas Data Colombia)
    PRIVACY_POLICY_VERSION: str = "v1.0-2026-LEY1581"

    # Almacenamiento Cloud opcional (Cloudinary / Supabase Storage)
    CLOUD_STORAGE_BUCKET_URL: str = "https://storage.ecoconecta.co/evidencias"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()


settings = get_settings()

