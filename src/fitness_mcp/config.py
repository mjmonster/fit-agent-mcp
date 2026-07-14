"""Configuration for Server A. All values come from env / .env — nothing hardcoded."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """fitness-mcp settings (env prefix: FITNESS_MCP_)."""

    model_config = SettingsConfigDict(env_prefix="FITNESS_MCP_", env_file=".env", extra="ignore")

    jwt_secret: str  # REQUIRED — the HS256 signing secret; never defaulted in code
    db_path: str = "fitness.db"
    host: str = "127.0.0.1"
    port: int = 8000


def get_settings() -> Settings:
    """Load settings from the environment. Raises if required values are missing."""
    return Settings()
