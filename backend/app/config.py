from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "NetTransform AI Backend"
    api_prefix: str = "/api"
    # CORS origins: allowing 8080 (dev) and 5173 (vite default)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://10.239.62.162:8080" # From screenshot
    ]

settings = Settings()
