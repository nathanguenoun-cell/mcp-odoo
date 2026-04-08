"""
Shared helpers for all tool modules.

Because Streamable HTTP is stateless, we cannot use a thread-local or global
OdooClient.  Instead, tools that need a client should call `client_from_ctx(ctx)`
which extracts the user credentials injected by BearerTokenMiddleware.

NOTE: FastMCP's Context object does not directly expose the raw Starlette Request.
We work around this by extracting credentials from the MCP request's HTTP headers
via a lightweight dependency.  For simplicity in this version, tools accept
optional `odoo_username` and `odoo_api_key` parameters or fall back to admin creds.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..odoo_client import OdooClient, get_client_for_request
from ..config import settings


def admin_client() -> OdooClient:
    """Return a client using the configured admin credentials."""
    return get_client_for_request(
        settings.odoo_admin_username, settings.odoo_admin_api_key
    )


def user_client(odoo_username: str | None, odoo_api_key: str | None) -> OdooClient:
    """Return a client for the given user credentials (or admin if None)."""
    return get_client_for_request(odoo_username, odoo_api_key)


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
