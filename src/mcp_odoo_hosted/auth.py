"""
OAuth 2.0 Authorization Server — mcp-odoo-hosted

Implémente le flow complet attendu par Dust (et tout client MCP 2025-03-26) :

  1. GET  /.well-known/oauth-protected-resource   RFC 9728  (Dust cherche ici EN PREMIER)
  2. GET  /.well-known/oauth-authorization-server  RFC 8414
  3. POST /oauth/register                          RFC 7591 — Dynamic Client Registration
                                                   (Dust s'auto-enregistre ici)
  4. GET  /oauth/authorize                         Authorization Code + PKCE
  5. POST /oauth/token                             Échange code → JWT
  6. POST /oauth/revoke                            RFC 7009

Flow Dust "Automatic" :
  Dust → /.well-known/oauth-protected-resource
       → /.well-known/oauth-authorization-server
       → POST /oauth/register  (obtient client_id + client_secret)
       → redirige l'utilisateur vers /oauth/authorize
       → l'utilisateur saisit ses credentials Odoo
       → redirect vers Dust avec le code
       → POST /oauth/token  (échange code + PKCE → JWT avec credentials Odoo)
       → toutes les requêtes MCP utilisent ce JWT
"""
from __future__ import annotations

import base64
import hashlib
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
from .context import odoo_api_key_var, odoo_username_var


def _base_url(request: Request) -> str:
    """Return the server's public base URL.

    Uses SERVER_URL from config when set; otherwise auto-detects from the
    incoming request's scheme and host (handles Railway/proxy URL changes).
    """
    if settings.server_url:
        return settings.server_url
    return f"{request.url.scheme}://{request.url.netloc}"


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

# Authorization codes
# code -> {client_id, odoo_username, odoo_api_key, redirect_uri,
#          code_challenge, code_challenge_method, expires_at, used}
_code_store: dict[str, dict] = {}

# Revoked JWT identifiers
_revoked_jtis: set[str] = set()

# Dynamically registered clients (RFC 7591)
# client_id -> {client_secret, redirect_uris, registered_at}
_dynamic_clients: dict[str, dict] = {}


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
    payload: dict = {
        "iss": settings.server_url,
        "sub": sub,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if odoo_username:
        payload["odoo_username"] = odoo_username
    if odoo_api_key:
        payload["odoo_api_key"] = odoo_api_key
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("jti") in _revoked_jtis:
            return None
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# PKCE helpers (RFC 7636)
# ---------------------------------------------------------------------------

def _verify_pkce(code_challenge: str, code_challenge_method: str, code_verifier: str) -> bool:
    if code_challenge_method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(expected, code_challenge)
    if code_challenge_method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


# ---------------------------------------------------------------------------
# Client validation (static + dynamically registered)
# ---------------------------------------------------------------------------

def _validate_client(client_id: str, client_secret: str) -> bool:
    """Vérifie les credentials d'un client (statique ou enregistré dynamiquement)."""
    # Client statique configuré via variables d'environnement
    if secrets.compare_digest(client_id, settings.oauth_client_id) and \
       secrets.compare_digest(client_secret, settings.oauth_client_secret):
        return True
    # Client enregistré dynamiquement (Dust, etc.)
    entry = _dynamic_clients.get(client_id)
    if entry and secrets.compare_digest(client_secret, entry["client_secret"]):
        return True
    return False


def _client_exists(client_id: str) -> bool:
    return client_id == settings.oauth_client_id or client_id in _dynamic_clients


# ---------------------------------------------------------------------------
# OAuth 2.0 endpoint handlers
# ---------------------------------------------------------------------------

async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 — Dust appelle cet endpoint EN PREMIER pour découvrir l'auth server."""
    base = _base_url(request)
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
    })


async def oauth_metadata(request: Request) -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "registration_endpoint": f"{base}/oauth/register",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "response_types_supported": ["code"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none",
        ],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": ["mcp"],
        "subject_types_supported": ["public"],
    })


async def oauth_register(request: Request) -> JSONResponse:
    """RFC 7591 — Dynamic Client Registration.
    Dust s'enregistre ici automatiquement pour obtenir un client_id/secret.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    client_id = secrets.token_urlsafe(16)
    client_secret = secrets.token_urlsafe(32)

    _dynamic_clients[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": body.get("redirect_uris", []),
        "registered_at": time.time(),
    }

    now = int(time.time())
    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": now,
        "client_secret_expires_at": 0,          # 0 = never expires (RFC 7591 §3.2.1)
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
        "scope": "mcp",
    }, status_code=201)


async def oauth_authorize(request: Request) -> Response:
    """Authorization endpoint — affiche un formulaire de login Odoo à l'utilisateur."""
    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    response_type = params.get("response_type", "code")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    # Validation client
    if not _client_exists(client_id):
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)

    if request.method == "GET":
        return HTMLResponse(_login_form_html(client_id, redirect_uri, state,
                                             code_challenge, code_challenge_method))

    # POST — traitement du formulaire
    form = await request.form()
    odoo_username = str(form.get("odoo_username", "")).strip()
    odoo_api_key = str(form.get("odoo_api_key", "")).strip()

    if not odoo_username or not odoo_api_key:
        return HTMLResponse(
            _login_form_html(client_id, redirect_uri, state,
                             code_challenge, code_challenge_method,
                             error="Email et clé API requis."),
            status_code=400,
        )

    from .odoo_client import validate_odoo_credentials
    if not validate_odoo_credentials(odoo_username, odoo_api_key):
        return HTMLResponse(
            _login_form_html(client_id, redirect_uri, state,
                             code_challenge, code_challenge_method,
                             error="Credentials Odoo invalides. Vérifiez votre email et votre clé API."),
            status_code=401,
        )

    code = secrets.token_urlsafe(32)
    _code_store[code] = {
        "client_id": client_id,
        "odoo_username": odoo_username,
        "odoo_api_key": odoo_api_key,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires_at": time.time() + 300,
        "used": False,
    }

    qs = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}?{qs}", status_code=302)


async def oauth_token(request: Request) -> JSONResponse:
    """Token endpoint — échange un code ou des credentials contre un JWT."""
    form = await request.form()
    grant_type = str(form.get("grant_type", "")).strip()

    # Résolution des credentials client
    client_id = str(form.get("client_id", "")).strip()
    client_secret = str(form.get("client_secret", "")).strip()

    # Support HTTP Basic Auth
    if not client_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode()
                client_id, _, client_secret = decoded.partition(":")
            except Exception:
                pass

    # ── Authorization Code flow ────────────────────────────────────────────
    if grant_type == "authorization_code":
        code = str(form.get("code", "")).strip()
        code_verifier = str(form.get("code_verifier", "")).strip()
        entry = _code_store.get(code)

        if not entry:
            return JSONResponse({"error": "invalid_grant",
                                 "error_description": "Code inconnu"}, status_code=400)
        if entry["used"]:
            return JSONResponse({"error": "invalid_grant",
                                 "error_description": "Code déjà utilisé"}, status_code=400)
        if time.time() > entry["expires_at"]:
            return JSONResponse({"error": "invalid_grant",
                                 "error_description": "Code expiré"}, status_code=400)
        if entry["client_id"] != client_id:
            return JSONResponse({"error": "invalid_grant",
                                 "error_description": "Client mismatch"}, status_code=400)

        # Vérification PKCE si utilisée
        if entry.get("code_challenge"):
            if not code_verifier:
                return JSONResponse({"error": "invalid_grant",
                                     "error_description": "code_verifier manquant"}, status_code=400)
            if not _verify_pkce(entry["code_challenge"], entry["code_challenge_method"], code_verifier):
                return JSONResponse({"error": "invalid_grant",
                                     "error_description": "PKCE invalide"}, status_code=400)

        # Validation client (optionnelle pour les clients publics PKCE)
        if client_secret and not _validate_client(client_id, client_secret):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        entry["used"] = True
        token = _create_access_token(
            sub=entry["odoo_username"],
            odoo_username=entry["odoo_username"],
            odoo_api_key=entry["odoo_api_key"],
        )
        return JSONResponse({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "scope": "mcp",
        })

    # ── Client Credentials flow ────────────────────────────────────────────
    if grant_type == "client_credentials":
        if not _validate_client(client_id, client_secret):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        token = _create_access_token(
            sub=client_id,
            odoo_username=settings.odoo_admin_username,
            odoo_api_key=settings.odoo_admin_api_key,
        )
        return JSONResponse({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "scope": "mcp",
        })

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

_OPEN_PATHS = frozenset([
    "/",
    "/health",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-authorization-server",
    "/mcp/.well-known/oauth-protected-resource",
    "/mcp/.well-known/oauth-authorization-server",
    "/oauth/register",
    "/oauth/authorize",
    "/oauth/token",
    "/oauth/revoke",
])


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            # WWW-Authenticate avec resource_metadata pour la découverte primaire
            base = _base_url(request)
            return JSONResponse(
                {"error": "unauthorized", "error_description": "Bearer token requis."},
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer realm="{base}", '
                        f'resource_metadata="{base}/.well-known/oauth-protected-resource"'
                    )
                },
            )

        payload = verify_token(auth[7:])
        if payload is None:
            return JSONResponse(
                {"error": "invalid_token", "error_description": "Token invalide ou expiré."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        # Inject credentials into the async context so FastMCP tool handlers
        # can access them via odoo_username_var / odoo_api_key_var.
        # Starlette's BaseHTTPMiddleware calls copy_context() inside call_next,
        # so values set here are inherited by the inner app task.
        odoo_username_var.set(payload.get("odoo_username"))
        odoo_api_key_var.set(payload.get("odoo_api_key"))

        request.state.odoo_username = payload.get("odoo_username")
        request.state.odoo_api_key = payload.get("odoo_api_key")
        request.state.token_sub = payload.get("sub")
        return await call_next(request)


# ---------------------------------------------------------------------------
# Login form HTML
# ---------------------------------------------------------------------------

def _login_form_html(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    error: Optional[str] = None,
) -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Connexion Odoo — MCP</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, sans-serif; background: #f0f2f5;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; }}
    .card {{ background: white; padding: 2.5rem; border-radius: 12px; width: 380px;
             box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
    .logo {{ font-size: 2rem; margin-bottom: 0.5rem; }}
    h1 {{ font-size: 1.25rem; margin-bottom: 0.25rem; color: #1a1a1a; }}
    .subtitle {{ font-size: .875rem; color: #666; margin-bottom: 1.5rem; }}
    label {{ display: block; font-size: .875rem; font-weight: 500;
             margin-bottom: .375rem; color: #374151; }}
    input {{ width: 100%; padding: .625rem .875rem; border: 1.5px solid #d1d5db;
             border-radius: 6px; font-size: 1rem; margin-bottom: 1rem;
             transition: border-color .15s; outline: none; }}
    input:focus {{ border-color: #714B67; }}
    .hint {{ font-size: .75rem; color: #9ca3af; margin-top: -.75rem;
             margin-bottom: 1rem; }}
    button {{ width: 100%; padding: .75rem; background: #714B67; color: white;
              border: none; border-radius: 6px; font-size: 1rem; font-weight: 600;
              cursor: pointer; transition: background .15s; }}
    button:hover {{ background: #5d3d56; }}
    .error {{ color: #dc2626; font-size: .875rem; margin-bottom: 1rem;
              padding: .625rem; background: #fef2f2; border-radius: 6px; }}
  </style>
</head>
<body>
<div class="card">
  <div class="logo">🔗</div>
  <h1>Connecter votre compte Odoo</h1>
  <p class="subtitle">Autorisez l'accès à votre instance Odoo</p>
  {error_html}
  <form method="POST">
    <input type="hidden" name="client_id" value="{client_id}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="code_challenge" value="{code_challenge}">
    <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
    <label for="odoo_username">Email Odoo</label>
    <input id="odoo_username" name="odoo_username" type="email"
           placeholder="vous@societe.com" required autocomplete="username">
    <label for="odoo_api_key">Clé API Odoo</label>
    <input id="odoo_api_key" name="odoo_api_key" type="password"
           placeholder="Votre clé API" required autocomplete="current-password">
    <p class="hint">Générez une clé API dans Odoo → Paramètres → Clés API</p>
    <button type="submit">Autoriser l'accès</button>
  </form>
</div>
</body>
</html>"""
