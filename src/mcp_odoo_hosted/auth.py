"""
OAuth 2.0 Authorization Server implementation for mcp-odoo-hosted.

Supports:
  • Authorization Code flow  — end-users authenticate with their own Odoo API key
    and receive a JWT that encodes their Odoo credentials.  This means every MCP
    tool call runs under *that user's* Odoo permissions.
  • Client Credentials flow  — server-to-server use-cases where a single admin
    account is acceptable (e.g. cron jobs, internal tools).

Endpoints
---------
GET  /.well-known/oauth-authorization-server   RFC 8414 metadata
GET  /oauth/authorize                          Authorization endpoint
POST /oauth/token                              Token endpoint
POST /oauth/revoke                             Token revocation (RFC 7009)
"""
from __future__ import annotations

import base64
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .config import settings

# ---------------------------------------------------------------------------
# In-memory stores  (replace with a database for production multi-instance)
# ---------------------------------------------------------------------------

# code_store[code] = {"client_id": ..., "odoo_username": ..., "odoo_api_key": ...,
#                      "expires_at": timestamp, "used": bool}
_code_store: dict[str, dict] = {}

# token_revocation_list: set of jti values that have been revoked
_revoked_jtis: set[str] = set()


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_access_token(
    *,
    sub: str,
    scope: str = "mcp",
    odoo_username: Optional[str] = None,
    odoo_api_key: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    jti = secrets.token_urlsafe(16)
    payload: dict = {
        "sub": sub,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
        "iss": settings.server_url,
    }
    if odoo_username:
        payload["odoo_username"] = odoo_username
    if odoo_api_key:
        payload["odoo_api_key"] = odoo_api_key
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT.  Returns payload or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        if payload.get("jti") in _revoked_jtis:
            return None
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# OAuth 2.0 endpoint handlers
# ---------------------------------------------------------------------------

async def oauth_metadata(request: Request) -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata."""
    base = settings.server_url
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "revocation_endpoint": f"{base}/oauth/revoke",
            "grant_types_supported": ["authorization_code", "client_credentials"],
            "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["mcp"],
        }
    )


async def oauth_authorize(request: Request) -> Response:
    """Authorization endpoint — shows a login form for the end-user."""
    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    response_type = params.get("response_type", "code")

    # Validate client
    if not secrets.compare_digest(client_id, settings.oauth_client_id):
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)

    if request.method == "GET":
        # Show login form
        html = _login_form_html(client_id, redirect_uri, state)
        return HTMLResponse(html)

    # POST — process form submission
    form = await request.form()
    odoo_username = str(form.get("odoo_username", "")).strip()
    odoo_api_key = str(form.get("odoo_api_key", "")).strip()

    if not odoo_username or not odoo_api_key:
        html = _login_form_html(
            client_id, redirect_uri, state, error="Username and API key are required."
        )
        return HTMLResponse(html, status_code=400)

    # Validate credentials against Odoo
    from .odoo_client import validate_odoo_credentials

    if not validate_odoo_credentials(odoo_username, odoo_api_key):
        html = _login_form_html(
            client_id, redirect_uri, state, error="Invalid Odoo credentials."
        )
        return HTMLResponse(html, status_code=401)

    # Issue authorization code
    code = secrets.token_urlsafe(32)
    _code_store[code] = {
        "client_id": client_id,
        "odoo_username": odoo_username,
        "odoo_api_key": odoo_api_key,
        "expires_at": time.time() + 300,  # 5 minutes
        "used": False,
    }

    qs = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}?{qs}", status_code=302)


async def oauth_token(request: Request) -> JSONResponse:
    """Token endpoint — exchange code or client credentials for a JWT."""
    form = await request.form()
    grant_type = str(form.get("grant_type", "")).strip()

    # ── Resolve client credentials ─────────────────────────────────────
    client_id = str(form.get("client_id", "")).strip()
    client_secret = str(form.get("client_secret", "")).strip()

    # Also support HTTP Basic Auth
    if not client_id or not client_secret:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode()
                client_id, _, client_secret = decoded.partition(":")
            except Exception:
                pass

    if not secrets.compare_digest(client_id or "", settings.oauth_client_id) or not secrets.compare_digest(
        client_secret or "", settings.oauth_client_secret
    ):
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    # ── Authorization Code flow ────────────────────────────────────────
    if grant_type == "authorization_code":
        code = str(form.get("code", "")).strip()
        entry = _code_store.get(code)

        if not entry:
            return JSONResponse({"error": "invalid_grant", "error_description": "Unknown code"}, status_code=400)
        if entry["used"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "Code already used"}, status_code=400)
        if time.time() > entry["expires_at"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, status_code=400)
        if entry["client_id"] != client_id:
            return JSONResponse({"error": "invalid_grant", "error_description": "Client mismatch"}, status_code=400)

        entry["used"] = True

        token = _create_access_token(
            sub=entry["odoo_username"],
            scope="mcp",
            odoo_username=entry["odoo_username"],
            odoo_api_key=entry["odoo_api_key"],
        )
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": settings.access_token_expire_minutes * 60,
                "scope": "mcp",
            }
        )

    # ── Client Credentials flow (admin / service account) ─────────────
    if grant_type == "client_credentials":
        token = _create_access_token(
            sub=client_id,
            scope="mcp",
            odoo_username=settings.odoo_admin_username,
            odoo_api_key=settings.odoo_admin_api_key,
        )
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": settings.access_token_expire_minutes * 60,
                "scope": "mcp",
            }
        )

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


async def oauth_revoke(request: Request) -> Response:
    """RFC 7009 — Token Revocation."""
    form = await request.form()
    token = str(form.get("token", "")).strip()
    payload = verify_token(token)
    if payload and payload.get("jti"):
        _revoked_jtis.add(payload["jti"])
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Bearer token middleware
# ---------------------------------------------------------------------------

_OPEN_PATHS = frozenset(
    [
        "/.well-known/oauth-authorization-server",
        "/oauth/token",
        "/oauth/authorize",
        "/oauth/revoke",
        "/health",
        "/",
    ]
)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Validate Bearer JWT on all paths except the OAuth + health endpoints."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "unauthorized",
                    "error_description": "A Bearer token is required.",
                },
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer realm="{settings.server_url}", '
                        'scope="mcp", '
                        f'error="unauthorized"'
                    )
                },
            )

        payload = verify_token(auth[7:])
        if payload is None:
            return JSONResponse(
                {
                    "error": "invalid_token",
                    "error_description": "Token is invalid or has expired.",
                },
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        # Attach user context so tools can pick up per-user Odoo credentials
        request.state.odoo_username = payload.get("odoo_username")
        request.state.odoo_api_key = payload.get("odoo_api_key")
        request.state.token_sub = payload.get("sub")

        return await call_next(request)


# ---------------------------------------------------------------------------
# Login form HTML (minimal, customize to match your brand)
# ---------------------------------------------------------------------------

def _login_form_html(
    client_id: str,
    redirect_uri: str,
    state: str,
    error: Optional[str] = None,
) -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in — Odoo MCP</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #f5f5f5;
            display: flex; align-items: center; justify-content: center; min-height: 100vh; margin:0; }}
    .card {{ background: white; padding: 2rem; border-radius: 8px; width: 360px;
             box-shadow: 0 2px 12px rgba(0,0,0,.1); }}
    h1 {{ margin: 0 0 1.5rem; font-size: 1.25rem; }}
    label {{ display: block; font-size: .875rem; margin-bottom: .25rem; color: #555; }}
    input {{ width: 100%; box-sizing: border-box; padding: .5rem .75rem;
             border: 1px solid #ddd; border-radius: 4px; font-size: 1rem; margin-bottom: 1rem; }}
    button {{ width: 100%; padding: .6rem; background: #714B67; color: white;
              border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #5d3d56; }}
    .error {{ color: #c0392b; font-size: .875rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
<div class="card">
  <h1>🔗 Connect your Odoo account</h1>
  {error_html}
  <form method="POST">
    <input type="hidden" name="client_id" value="{client_id}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <label for="odoo_username">Odoo email</label>
    <input id="odoo_username" name="odoo_username" type="email"
           placeholder="you@company.com" required autocomplete="username">
    <label for="odoo_api_key">Odoo API key</label>
    <input id="odoo_api_key" name="odoo_api_key" type="password"
           placeholder="Your Odoo API key" required autocomplete="current-password">
    <button type="submit">Authorize</button>
  </form>
</div>
</body>
</html>"""
