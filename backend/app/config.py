from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Local development keeps the Vite/Supabase settings in the repository root.
    # Load those as a fallback, while allowing backend/.env to override them.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    project_name: str = "NetTransform AI Backend"
    api_prefix: str = "/api"
    # CORS origins: allowing 8080 (dev) and 5173 (vite default)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://10.239.62.162:8080" # From screenshot
    ]
    supabase_url: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL", "VITE_SUPABASE_URL"))
    supabase_publishable_key: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY"))

settings = Settings()
