from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""
    llm_timeout_seconds: float = 15
    llm_max_retries: int = 2
    llm_max_tokens: int = 1800
    insforge_url: str = ""
    insforge_api_key: SecretStr = SecretStr("")
    insforge_anon_key: SecretStr = SecretStr("")
    session_cookie_secure: bool = False  # True when serving the UI/API over HTTPS.
    kubeconfig_path: str = ""
    kubectl_timeout_seconds: int = 10
    investigation_timeout_seconds: int = 90
    stuck_pod_seconds: int = 300
    max_log_requests: int = 12
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
