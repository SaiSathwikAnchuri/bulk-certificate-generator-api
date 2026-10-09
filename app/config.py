"""Application configuration settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/certificates"
    test_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/certificates_test"
    storage_dir: str = "storage/certificates"
    max_recipients: int = 1000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
