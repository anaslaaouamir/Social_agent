"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import Literal
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic import Field, field_validator


class CustomDotEnvSettingsSource(DotEnvSettingsSource):
    """Support comma-separated ALLOWED_HOSTS in .env files."""

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name == "allowed_hosts" and isinstance(value, str):
            raw = value.strip()
            if raw and not raw.startswith("["):
                return [item.strip() for item in raw.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        
    )

    # Core
    secret_key: str = Field(..., min_length=32)
    debug: bool = False
    environment: Literal["development", "production", "test"] = "production"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]

    # Database
    database_url: str = "postgresql+asyncpg://agent:agentpass@localhost:5432/social_agent"
    sync_database_url: str = "postgresql://agent:agentpass@localhost:5432/social_agent"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    
    # Grafana / Prometheus
    prometheus_port: int = 9091

    # Slack alerts
    slack_webhook_url: str = ""
    slack_alert_channel: str = "#social-agent-alerts"

    # RAG / ChromaDB
    chroma_db_path: str = "./data/chroma"
    rag_collection_name: str = "social_knowledge"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"

    # AI APIs
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    hugging_face_api: str = ""

    # Social Platforms
    instagram_access_token: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = "http://localhost:8000/api/auth/instagram/callback"
    instagram_manual_account_id: str = ""
    instagram_manual_account_username: str = ""
    instagram_manual_access_token: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    linkedin_access_token: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/auth/linkedin/callback"
    facebook_access_token: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_redirect_uri: str = "http://localhost:8000/api/auth/facebook/callback"
    threads_app_id: str = ""
    threads_app_secret: str = ""
    threads_redirect_uri: str = "http://localhost:8000/api/auth/threads/callback"
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8000/api/auth/youtube/callback"
    twitter_api_key: str = ""
    twitter_api_secret_key: str = ""
    twitter_bearer_token: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    twitter_refresh_token: str = ""
    twitter_redirect_uri: str = "http://localhost:8000/api/auth/twitter/callback"
    frontend_url: str = "http://localhost:3000"
    public_api_base_url: str = ""
    meta_webhook_verify_token: str = ""
    github_token: str = ""
    github_video_repo: str = ""

    # Storage
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "social-agent-media"
    imgbb_api_key: str = ""

    # Notifications
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email: str = ""

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Feature Flags
    direct_access_mode: bool = True
    enable_auto_posting: bool = True
    enable_auto_reply: bool = False
    enable_crisis_alerts: bool = True
    crisis_negative_threshold: float = 0.4
    crisis_volume_multiplier: float = 3.0

    # Pinterest
    pinterest_app_id: str = ""
    pinterest_app_secret: str = ""
    pinterest_redirect_uri: str = "http://localhost:8000/api/auth/pinterest/callback"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> bool:
        """Accept common string env values like 'release'/'debug'."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "0", "false", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "1", "true", "yes", "on"}:
                return True
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            CustomDotEnvSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
