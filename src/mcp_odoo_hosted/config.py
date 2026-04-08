"""Configuration management via environment variables."""
from __future__ import annotations

import secrets
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Odoo ──────────────────────────────────────────────────────────────
    odoo_url: str = Field(..., description="Odoo instance URL, e.g. https://mycompany.odoo.com")
    odoo_db: str = Field(..., description="Odoo database name")

    # ── OAuth 2.0 ─────────────────────────────────────────────────────────
    # For Authorization Code flow, each user will have their own Odoo API key
    # stored in the user store. These are the defaults / admin credentials.
    odoo_admin_username: str = Field(..., description="Odoo admin username (email)")
    odoo_admin_api_key: str = Field(..., description="Odoo admin API key")

    # JWT signing secret (generate a strong random value in production)
    jwt_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for signing JWT access tokens",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # OAuth client app credentials (used by the web app to obtain tokens)
    oauth_client_id: str = Field(..., description="Client ID for your web application")
    oauth_client_secret: str = Field(..., description="Client secret for your web application")

    # ── Server ────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    # Public URL of this server, used in OAuth metadata (e.g. https://mcp.myapp.com)
    server_url: str = Field(..., description="Public base URL of this MCP server")

    # ── Redis (optional caching) ──────────────────────────────────────────
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    redis_default_ttl: int = 300  # seconds

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"

    @field_validator("server_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("odoo_url")
    @classmethod
    def strip_odoo_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
