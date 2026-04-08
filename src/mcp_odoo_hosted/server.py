"""
MCP Odoo Hosted — serveur principal

Endpoints
---------
  GET  /.well-known/oauth-protected-resource    RFC 9728 (Dust cherche ici EN PREMIER)
  GET  /.well-known/oauth-authorization-server  RFC 8414
  POST /oauth/register                          RFC 7591 — Dynamic Client Registration
  GET  /oauth/authorize                         Authorization Code + PKCE
  POST /oauth/token                             Échange code → JWT
  POST /oauth/revoke                            RFC 7009
  GET  /health                                  Health-check
  POST /mcp                                     Streamable HTTP MCP (MCP 2025-03-26)
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import (
    BearerTokenMiddleware,
    oauth_authorize,
    oauth_metadata,
    oauth_protected_resource_metadata,
    oauth_register,
    oauth_revoke,
    oauth_token,
)
from .config import settings

logger = logging.getLogger(__name__)

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
    stateless_http=True,
)

# ---------------------------------------------------------------------------
# Enregistrement des outils
# ---------------------------------------------------------------------------

from .tools.contacts import register as _reg_contacts
from .tools.expenses import register as _reg_expenses
from .tools.hr import register as _reg_hr
from .tools.invoices import register as _reg_invoices
from .tools.products import register as _reg_products
from .tools.projects import register as _reg_projects
from .tools.sales import register as _reg_sales
from .tools.timesheets import register as _reg_timesheets
from .tools.utilities import register as _reg_utilities

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
# Endpoints utilitaires
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "mcp-odoo-hosted"})


async def root(request: Request) -> JSONResponse:
    base = settings.server_url
    return JSONResponse({
        "name": "mcp-odoo-hosted",
        "mcp_endpoint": f"{base}/mcp",
        "oauth_metadata": f"{base}/.well-known/oauth-authorization-server",
        "protected_resource": f"{base}/.well-known/oauth-protected-resource",
    })


# ---------------------------------------------------------------------------
# Construction de l'application ASGI
# ---------------------------------------------------------------------------

def create_app() -> Starlette:
    mcp_asgi = mcp.streamable_http_app()

    routes = [
        Route("/", root),
        Route("/health", health),

        # RFC 9728 — exposé à la racine ET sous /mcp/ (certains clients dérivent
        # le chemin depuis l'URL du endpoint MCP)
        Route("/.well-known/oauth-protected-resource",
              oauth_protected_resource_metadata, methods=["GET"]),
        Route("/mcp/.well-known/oauth-protected-resource",
              oauth_protected_resource_metadata, methods=["GET"]),

        # RFC 8414
        Route("/.well-known/oauth-authorization-server",
              oauth_metadata, methods=["GET"]),
        Route("/mcp/.well-known/oauth-authorization-server",
              oauth_metadata, methods=["GET"]),

        # OAuth endpoints
        Route("/oauth/register", oauth_register, methods=["POST"]),
        Route("/oauth/authorize", oauth_authorize, methods=["GET", "POST"]),
        Route("/oauth/token", oauth_token, methods=["POST"]),
        Route("/oauth/revoke", oauth_revoke, methods=["POST"]),

        # MCP endpoint (Streamable HTTP)
        Mount("/mcp", app=mcp_asgi),
    ]

    middleware = [
        # CORS en premier pour que les preflight OPTIONS passent avant l'auth
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
        ),
        Middleware(BearerTokenMiddleware),
    ]

    app = Starlette(routes=routes, middleware=middleware)

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("=" * 50)
        logger.info("MCP Odoo Hosted — démarrage")
        logger.info("Endpoint MCP   : %s/mcp", settings.server_url)
        logger.info("OAuth metadata : %s/.well-known/oauth-authorization-server",
                    settings.server_url)
        logger.info("Client ID      : %s", settings.oauth_client_id)
        logger.info("Client Secret  : %s", settings.oauth_client_secret)
        logger.info("=" * 50)

    return app


app = create_app()
