"""
MCP Odoo Hosted — main server.

Architecture
------------
  POST /mcp              Streamable HTTP MCP endpoint (MCP 2025-03-26)
  GET  /.well-known/…    OAuth 2.0 Authorization Server metadata
  GET  /oauth/authorize  Authorization Code login page
  POST /oauth/token      Token endpoint (auth_code + client_credentials)
  POST /oauth/revoke     Token revocation
  GET  /health           Health-check

Every request to /mcp must carry a valid Bearer JWT.
The JWT encodes the user's Odoo credentials so each tool call runs
under *that user's* Odoo access rights.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import (
    BearerTokenMiddleware,
    oauth_authorize,
    oauth_metadata,
    oauth_revoke,
    oauth_token,
)
from .config import settings
from .odoo_client import get_client_for_request

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="mcp-odoo",
    instructions=(
        "You are connected to an Odoo ERP instance. "
        "You can manage timesheets, expenses, contacts, invoices, sales orders, "
        "products, and HR records on behalf of the authenticated user."
    ),
    stateless_http=True,  # Required for hosted/stateless deployment
)

# ---------------------------------------------------------------------------
# Register tools from all modules
# ---------------------------------------------------------------------------

from .tools.contacts import register as _reg_contacts  # noqa: E402
from .tools.expenses import register as _reg_expenses  # noqa: E402
from .tools.hr import register as _reg_hr  # noqa: E402
from .tools.invoices import register as _reg_invoices  # noqa: E402
from .tools.products import register as _reg_products  # noqa: E402
from .tools.projects import register as _reg_projects  # noqa: E402
from .tools.sales import register as _reg_sales  # noqa: E402
from .tools.timesheets import register as _reg_timesheets  # noqa: E402
from .tools.utilities import register as _reg_utilities  # noqa: E402

_reg_contacts(mcp)
_reg_expenses(mcp)
_reg_hr(mcp)
_reg_invoices(mcp)
_reg_products(mcp)
_reg_projects(mcp)
_reg_sales(mcp)
_reg_timesheets(mcp)
_reg_utilities(mcp)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "mcp-odoo-hosted"})


async def root(request: Request) -> JSONResponse:
    base = settings.server_url
    return JSONResponse(
        {
            "name": "mcp-odoo-hosted",
            "mcp_endpoint": f"{base}/mcp",
            "auth_metadata": f"{base}/.well-known/oauth-authorization-server",
        }
    )


# ---------------------------------------------------------------------------
# Build the combined ASGI application
# ---------------------------------------------------------------------------

def create_app() -> Starlette:
    mcp_asgi = mcp.streamable_http_app()

    routes = [
        Route("/", root),
        Route("/health", health),
        Route("/.well-known/oauth-authorization-server", oauth_metadata, methods=["GET"]),
        Route("/oauth/authorize", oauth_authorize, methods=["GET", "POST"]),
        Route("/oauth/token", oauth_token, methods=["POST"]),
        Route("/oauth/revoke", oauth_revoke, methods=["POST"]),
        Mount("/mcp", app=mcp_asgi),
    ]

    middleware = [
        Middleware(BearerTokenMiddleware),
    ]

    return Starlette(routes=routes, middleware=middleware)


app = create_app()
