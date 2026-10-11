from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "NetTransform AI Backend"
    api_prefix: str = "/api"
    ssh_host: Optional[str] = Field(default=None, validation_alias="SSH_HOST")
    ssh_port: int = Field(default=22, validation_alias="SSH_PORT")
    ssh_user: Optional[str] = Field(default=None, validation_alias="SSH_USER")
    ssh_password: Optional[str] = Field(default=None, validation_alias="SSH_PASSWORD")
    ssh_key_path: Optional[str] = Field(default=None, validation_alias="SSH_KEY_PATH")
    ssh_connect_timeout: float = Field(default=5.0, validation_alias="SSH_CONNECT_TIMEOUT", gt=0, le=60)
    mininet_check_command: str = Field(default="command -v mn", validation_alias="MININET_CHECK_COMMAND")
    # CORS origins: allowing 8080 (dev) and 5173 (vite default)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://10.239.62.162:8080" # From screenshot
    ]

settings = Settings()
