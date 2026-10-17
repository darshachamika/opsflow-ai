from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.config import PROJECT_ROOT


class LLMSettings(BaseSettings):
    gemini_enabled: bool = False
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = Field(default="gemini-flash-latest", pattern=r"^[A-Za-z0-9._-]{1,100}$")
    gemini_timeout_seconds: float = Field(default=15, ge=1, le=60)
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")


llm_settings = LLMSettings()
