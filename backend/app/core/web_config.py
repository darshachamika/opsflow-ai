"""Browser access settings; bearer authentication still applies to requests."""
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.config import PROJECT_ROOT


class WebSettings(BaseSettings):
    cors_allowed_origins: list[str] = Field(default_factory=list)
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment
                    or origin != origin.strip() or "*" in origin):
                raise ValueError("CORS origins must be exact HTTP(S) origins without paths or wildcards.")
            _ = parsed.port
        return list(dict.fromkeys(origins))


web_settings = WebSettings()
