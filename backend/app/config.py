from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    project_name: str = "NexusTwin Backend"
    api_prefix: str = "/api"
    # CORS origins: allowing 8080 (dev) and 5173 (vite default)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://10.239.62.162:8080" # From screenshot
    ]

    class Config:
        env_file = ".env"

settings = Settings()
