"""Application settings, loaded from environment / .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the project root regardless of CWD (apps/api/rentwise/ → ../../../../.env)
_ENV_FILE = Path(__file__).parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Read from environment variables and `.env`. Last source wins."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "RentWise"
    app_version: str = "0.1.0"
    environment: str = Field(default="dev", description="dev | prod")
    debug: bool = True

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/rentwise.db"

    # --- LLM (LiteLLM) ---
    # See docs/llm-providers.md for full options.
    rentwise_llm_model: str = "openrouter/qwen/qwen-2.5-72b-instruct:free"
    rentwise_llm_fallback_model: str | None = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    rentwise_llm_timeout_seconds: int = 30
    rentwise_llm_max_retries: int = 2

    # API keys — only set whichever provider you use.
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- HTTP client identity (for adapters) ---
    user_agent: str = "RentWise/0.1 (+https://github.com/ylee89/rentwise; contact@example.com)"

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8081"]


settings = Settings()


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist."""
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
