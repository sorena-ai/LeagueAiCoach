from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"  # Legacy, kept for backward compatibility
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "onyx"
    openai_tts_speed: float = 1.2

    # Coach LLM Configuration
    coach_provider: Literal["gemini", "grok", "openai"] = "gemini"  # Which LLM provider to use for coaching
    coach_model: str = "gemini-flash-lite-latest"  # Model name for the selected provider

    # Google Gemini Configuration
    google_api_key: str  # Google/Gemini API key
    gemini_model: str = "gemini-flash-lite-latest"  # Gemini Flash Lite model (legacy, use coach_model instead)

    # Grok Configuration
    grok_api_key: str
    grok_model: str = "grok-3"  # Grok model (legacy, use coach_model instead)

    # Application Configuration
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "DEBUG"

    # Datadog Configuration
    datadog_api_key: Optional[str] = Field(  # DD ingestion key
        default=None,
        validation_alias=AliasChoices("DATADOG_API_KEY", "DD_API_KEY"),
    )
    datadog_app_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("DATADOG_APP_KEY", "DD_APP_KEY"),
    )
    datadog_service: str = Field(
        default="sensei-lol-coach",
        validation_alias=AliasChoices("DATADOG_SERVICE", "DD_SERVICE"),
    )
    datadog_env: str = Field(
        default="development",
        validation_alias=AliasChoices("DATADOG_ENV", "DD_ENV"),
    )
    datadog_site: str = Field(
        default="datadoghq.eu",
        validation_alias=AliasChoices("DATADOG_SITE", "DD_SITE"),
    )
    datadog_version: str = Field(
        default="1.0.0",
        validation_alias=AliasChoices("DATADOG_VERSION", "DD_VERSION"),
    )
    datadog_logs_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DATADOG_LOGS_ENABLED", "DD_LOGS_ENABLED"),
    )
    datadog_log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("DATADOG_LOG_LEVEL", "DD_LOG_LEVEL"),
    )

    # API Configuration
    max_file_size_mb: int = 10
    max_game_stats_kb: int = 50  # Maximum size for game_stats JSON in KB
    request_timeout_seconds: int = 30
    cors_allowed_origins: str = ""

    # MongoDB
    mongodb_uri: str = "mongodb://mongodb:27017/sensii"
    mongodb_db_name: str = "sensii"

    # Auth0 / login
    auth0_domain: str = ""
    auth0_client_id: str = ""
    auth0_client_secret: str = ""
    auth0_audience: str = ""
    auth0_callback_url: str = ""
    login_base_url: str = ""
    login_success_url: str = ""

    # Session tokens
    session_token_secret: str = "replace-me"
    session_token_issuer: str = "sensii-api"
    session_token_audience: str = "sensii-client"
    session_token_expires_minutes: int = 60
    refresh_token_expires_days: int = 30
    auth_session_ttl_seconds: int = 600

    # Paths
    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path(__file__).parent.parent / "data"

    @property
    def champions_dir(self) -> Path:
        """Get the champions directory path containing individual champion XML files."""
        return self.data_dir / "champions"

    @property
    def champion_combos_dir(self) -> Path:
        """Get the champion combos directory path containing champion combo XML files."""
        return self.data_dir / "champion-combos"

    @property
    def champion_builds_dir(self) -> Path:
        """Get the champion builds directory path containing champion build directories."""
        return self.data_dir / "champion-builds"

    @property
    def champion_guide_dir(self) -> Path:
        """Get the champion guide directory path containing champion guide directories."""
        return self.data_dir / "champion-guide"

    @property
    def playbook_dir(self) -> Path:
        """Get the playbook directory path containing strategic playbook files."""
        return self.data_dir / "playbook"

    @property
    def downloads_dir(self) -> Path:
        """Get the downloads directory path for serving release files."""
        return Path(__file__).parent.parent / "downloads"

    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size from MB to bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_game_stats_bytes(self) -> int:
        """Convert max game stats size from KB to bytes."""
        return self.max_game_stats_kb * 1024

    @property
    def allowed_origins(self) -> list[str]:
        """Return configured CORS origins."""
        origins: list[str] = []
        if self.login_base_url:
            origins.append(self.login_base_url.rstrip("/"))
        if self.login_success_url:
            base = self.login_success_url
            if "?" in base:
                base = base.split("?", 1)[0]
            origins.append(base.rstrip("/"))
        if self.cors_allowed_origins:
            for origin in self.cors_allowed_origins.split(","):
                trimmed = origin.strip()
                if trimmed:
                    origins.append(trimmed.rstrip("/"))
        # Remove duplicates while preserving order
        unique: list[str] = []
        for origin in origins:
            if origin not in unique:
                unique.append(origin)
        return unique or ["*"]


# Global settings instance
settings = Settings()
