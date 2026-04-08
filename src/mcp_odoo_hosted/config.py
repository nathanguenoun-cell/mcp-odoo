"""Configuration management via environment variables."""
from __future__ import annotations

import hashlib
import secrets
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Odoo ──────────────────────────────────────────────────────────────
    odoo_url: str = Field(..., description="Odoo instance URL, e.g. https://mycompany.odoo.com")
    odoo_db: str = Field(..., description="Odoo database name")

    # ── OAuth 2.0 ─────────────────────────────────────────────────────────
    odoo_admin_username: str = Field(..., description="Odoo admin username (email)")
    odoo_admin_api_key: str = Field(..., description="Odoo admin API key")

    # JWT signing secret — set JWT_SECRET_KEY in Railway to make tokens persistent
    jwt_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for signing JWT access tokens",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # OAuth client credentials — set OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET in Railway
    # If not set, they are derived deterministically from jwt_secret_key so they
    # remain stable across restarts as long as JWT_SECRET_KEY is fixed.
    oauth_client_id: str = Field(default="mcp-client")
    oauth_client_secret: str = Field(default="")  # filled by model_validator below

    # ── Server ────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    server_url: str = Field(..., description="Public base URL of this MCP server")

    # ── Redis (optional) ──────────────────────────────────────────────────
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    redis_default_ttl: int = 300

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator("server_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("odoo_url")
    @classmethod
    def strip_odoo_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @model_validator(mode="after")
    def derive_oauth_secret(self) -> "Settings":
        """
        Si oauth_client_secret est vide (variable non définie dans Railway),
        le dériver de jwt_secret_key de façon déterministe.
        On vérifie self.oauth_client_secret (lu par pydantic-settings)
        plutôt que os.environ pour éviter les problèmes de casse.
        """
        if not self.oauth_client_secret:
            self.oauth_client_secret = hashlib.sha256(
                f"oauth_client_secret:{self.jwt_secret_key}".encode()
            ).hexdigest()
        return self

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
