"""Configuration for Server B. All values come from env / .env — nothing hardcoded."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """coach-agent settings (env prefix: COACH_AGENT_)."""

    model_config = SettingsConfigDict(env_prefix="COACH_AGENT_", env_file=".env", extra="ignore")

    server_url: str = "http://127.0.0.1:8000/mcp"
    model: str = "claude-haiku-4-5"
    token: str = ""  # per-user JWT, minted by fitness-mcp issue-token; B only HOLDS it


def get_settings() -> Settings:
    """Load settings from the environment."""
    return Settings()
