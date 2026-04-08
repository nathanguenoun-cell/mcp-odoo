"""
Request-scoped context variables for Odoo credentials.

Starlette's BaseHTTPMiddleware uses copy_context() before spawning the inner
app task, so ContextVars set in dispatch() (before call_next) are visible
inside FastMCP tool handlers.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

odoo_username_var: ContextVar[Optional[str]] = ContextVar("odoo_username", default=None)
odoo_api_key_var: ContextVar[Optional[str]] = ContextVar("odoo_api_key", default=None)
