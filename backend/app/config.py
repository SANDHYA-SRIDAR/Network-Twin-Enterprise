from pathlib import Path
from urllib.parse import urlparse
import base64
import json

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
ENV_FILES = (ROOT_DIR / ".env", BACKEND_DIR / ".env")


def key_category(value: str | None) -> str:
    if not value:
        return "missing"
    if value.startswith("sb_publishable_"):
        return "publishable"
    if value.startswith("sb_secret_"):
        return "secret-not-allowed"
    try:
        # Classification only; user identity is ALWAYS validated by Supabase Auth.
        payload = json.loads(base64.urlsafe_b64decode(value.split(".")[1] + "=="))
        return "legacy-anon-jwt" if isinstance(payload, dict) and payload.get("role") == "anon" else "non-anon-jwt-not-allowed"
    except (ValueError, IndexError, TypeError):
        return "unrecognized"


class Settings(BaseSettings):
    # Absolute paths make startup identical from root, backend, uvicorn or an IDE.
    # backend/.env overrides root; process environment overrides both.
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    project_name: str = "NetTransform AI Backend"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:8080"]
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, repr=False, validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_anon_key: str | None = Field(default=None, repr=False, validation_alias="SUPABASE_ANON_KEY")
    supabase_project_id: str | None = Field(default=None, validation_alias="SUPABASE_PROJECT_ID")
    frontend_supabase_url: str | None = Field(default=None, validation_alias="VITE_SUPABASE_URL")
    frontend_supabase_key: str | None = Field(default=None, repr=False, validation_alias="VITE_SUPABASE_PUBLISHABLE_KEY")
    frontend_supabase_project_id: str | None = Field(default=None, validation_alias="VITE_SUPABASE_PROJECT_ID")
    assistant_url: str | None = None
    assistant_model: str | None = None
    assistant_api_key: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def public_key_fallbacks(self):
        # Separate fields preserve both values for conflict checking. AliasChoices
        # can consume VITE_* aliases and hide the conflicting frontend value.
        self.supabase_url = self.supabase_url or self.frontend_supabase_url
        self.supabase_publishable_key = self.supabase_publishable_key or self.frontend_supabase_key or self.supabase_anon_key
        self.supabase_project_id = self.supabase_project_id or self.frontend_supabase_project_id
        return self

    def supabase_configuration_error(self) -> str | None:
        if not self.supabase_url or not self.supabase_publishable_key:
            return "Supabase URL and public project key must be configured on the backend."
        parsed = urlparse(self.supabase_url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return "The configured Supabase URL is invalid."
        if key_category(self.supabase_publishable_key) not in {"publishable", "legacy-anon-jwt"}:
            return "Use a Supabase publishable key or legacy anon key, never a secret key or user token as the project key."
        if self.frontend_supabase_url and self.frontend_supabase_url.rstrip("/") != self.supabase_url.rstrip("/"):
            return "Backend and frontend Supabase URLs disagree. Synchronize the project configuration and restart the services."
        if self.frontend_supabase_key and self.frontend_supabase_key != self.supabase_publishable_key:
            return "Backend and frontend Supabase public keys disagree. Synchronize SUPABASE_PUBLISHABLE_KEY and VITE_SUPABASE_PUBLISHABLE_KEY and restart the services."
        ref = parsed.hostname.split(".")[0] if parsed.hostname.endswith(".supabase.co") else None
        for configured_ref in (self.supabase_project_id, self.frontend_supabase_project_id):
            if ref and configured_ref and ref != configured_ref:
                return "The configured Supabase project ID does not match the URL."
        return None

    def supabase_diagnostic(self) -> dict:
        host = urlparse(self.supabase_url or "").hostname
        return {"project_reference": host.split(".")[0] if host and host.endswith(".supabase.co") else None,
                "url_configured": bool(self.supabase_url), "key_configured": bool(self.supabase_publishable_key),
                "key_format": key_category(self.supabase_publishable_key),
                "configuration_valid": self.supabase_configuration_error() is None}


# Settings are loaded once per process; restart after changing environment values.
settings = Settings()
