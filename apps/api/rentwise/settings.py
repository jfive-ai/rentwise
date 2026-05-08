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

    # --- Search cache & paging ---
    search_cache_ttl_seconds: int = Field(
        default=900,
        validation_alias="RENTWISE_SEARCH_CACHE_TTL_SECONDS",
    )
    search_page_default: int = Field(
        default=50,
        validation_alias="RENTWISE_SEARCH_PAGE_DEFAULT",
    )
    search_page_max: int = Field(
        default=200,
        validation_alias="RENTWISE_SEARCH_PAGE_MAX",
    )

    # --- Craigslist ---
    craigslist_region: str = Field(
        default="vancouver",
        validation_alias="RENTWISE_CRAIGSLIST_REGION",
    )

    # --- LLM (LiteLLM) ---
    # See docs/llm-providers.md for full options.
    rentwise_llm_model: str = "openrouter/qwen/qwen-2.5-72b-instruct:free"
    rentwise_llm_fallback_model: str | None = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    rentwise_llm_timeout_seconds: int = 30
    rentwise_llm_max_retries: int = 2

    # --- Settings encryption ---
    # Fernet key used to encrypt secrets at rest (LLM API keys, etc.).
    # Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
    # Required for any settings persistence; tests provide a fixed key via monkeypatch.
    rentwise_settings_encryption_key: str | None = None

    # API keys — only set whichever provider you use.
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- HTTP client identity (for adapters) ---
    user_agent: str = "RentWise/0.1 (+https://github.com/ylee89/rentwise; contact@example.com)"

    # --- Phase 4 enrichment (geocoding) ---
    rentwise_geocode_enabled: bool = Field(
        default=True,
        validation_alias="RENTWISE_GEOCODE_ENABLED",
    )
    rentwise_geocode_timeout_seconds: float = Field(
        default=5.0,
        validation_alias="RENTWISE_GEOCODE_TIMEOUT_SECONDS",
    )
    rentwise_nominatim_base_url: str = Field(
        default="https://nominatim.openstreetmap.org",
        validation_alias="RENTWISE_NOMINATIM_BASE_URL",
    )
    rentwise_geocode_cache_ttl_days: int = Field(
        default=30,
        validation_alias="RENTWISE_GEOCODE_CACHE_TTL_DAYS",
    )

    # --- Phase 4 PR-C: photo hashing + dedup ---
    rentwise_photo_hash_enabled: bool = Field(
        default=True,
        validation_alias="RENTWISE_PHOTO_HASH_ENABLED",
    )
    rentwise_photo_hash_timeout_seconds: float = Field(
        default=5.0,
        validation_alias="RENTWISE_PHOTO_HASH_TIMEOUT_SECONDS",
    )
    rentwise_photo_hash_cache_ttl_days: int = Field(
        default=90,
        validation_alias="RENTWISE_PHOTO_HASH_CACHE_TTL_DAYS",
    )
    rentwise_dedup_enabled: bool = Field(
        default=True,
        validation_alias="RENTWISE_DEDUP_ENABLED",
    )
    rentwise_dedup_confidence_threshold: float = Field(
        default=0.7,
        validation_alias="RENTWISE_DEDUP_CONFIDENCE_THRESHOLD",
    )

    # --- Phase 5 PR-B: alerts + scheduler + SMTP ---
    rentwise_scheduler_enabled: bool = Field(
        default=False,
        validation_alias="RENTWISE_SCHEDULER_ENABLED",
        description="Off in CI/tests. Set to True to start the alert scheduler at app startup.",
    )
    rentwise_alerts_from: str = Field(
        default="RentWise <noreply@rentwise.local>",
        validation_alias="RENTWISE_ALERTS_FROM",
    )
    rentwise_alerts_app_base_url: str = Field(
        default="http://localhost:8081",
        validation_alias="RENTWISE_ALERTS_APP_BASE_URL",
    )
    rentwise_smtp_host: str | None = Field(default=None, validation_alias="RENTWISE_SMTP_HOST")
    rentwise_smtp_port: int = Field(default=587, validation_alias="RENTWISE_SMTP_PORT")
    rentwise_smtp_starttls: bool = Field(default=True, validation_alias="RENTWISE_SMTP_STARTTLS")
    rentwise_smtp_username: str | None = Field(
        default=None, validation_alias="RENTWISE_SMTP_USERNAME"
    )
    rentwise_smtp_password: str | None = Field(
        default=None, validation_alias="RENTWISE_SMTP_PASSWORD"
    )

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8081"]


settings = Settings()


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist."""
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
