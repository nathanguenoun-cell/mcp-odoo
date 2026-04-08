"""
Shared helpers for all tool modules.

Credentials are injected per-request via ContextVar by BearerTokenMiddleware.
Starlette copies the async context before running the inner app, so values set
in the middleware are visible inside FastMCP tool handlers.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..context import odoo_api_key_var, odoo_username_var
from ..odoo_client import OdooClient, get_client_for_request
from ..config import settings


def admin_client() -> OdooClient:
    """Return a client using the configured admin credentials."""
    return get_client_for_request(
        settings.odoo_admin_username, settings.odoo_admin_api_key
    )


def user_client() -> OdooClient:
    """Return a client for the current request's authenticated user.

    Reads Odoo credentials from the ContextVar populated by BearerTokenMiddleware.
    Falls back to admin credentials when no user-level credentials are present
    (e.g. client_credentials grant or unauthenticated admin token).
    """
    return get_client_for_request(odoo_username_var.get(), odoo_api_key_var.get())


def format_record(record: dict, fields: list[str]) -> dict:
    """Return a trimmed dict with only the requested fields."""
    return {k: v for k, v in record.items() if k in fields}


def many2one_name(value: Any) -> str | None:
    """Extract the display name from a Many2one field value ([id, name] or False)."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[1]
    return None


def many2one_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0]
    return None
