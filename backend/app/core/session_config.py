from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.config import PROJECT_ROOT

class SessionSettings(BaseSettings):
    session_cookie_secure: bool = False  # Local HTTP only; enable behind HTTPS.
    session_hours: int = Field(default=8, ge=1, le=24)
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / '.env', extra='ignore', env_file_encoding='utf-8')

session_settings = SessionSettings()
COOKIE_NAME = 'opsflow_session'
COOKIE_PATH = '/api/v1'
