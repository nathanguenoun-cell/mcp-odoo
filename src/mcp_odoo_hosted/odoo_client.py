"""
Odoo XML-RPC client.

Each tool call receives an OdooClient instance built from the *current user's*
credentials (extracted from the JWT by the auth middleware).  This ensures that
every operation runs under the authenticated user's Odoo access rights.
"""
from __future__ import annotations

import functools
import xmlrpc.client
from typing import Any, Optional

from .config import settings


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class OdooClient:
    """Thin wrapper around the Odoo XML-RPC 2 API."""

    def __init__(self, username: str, api_key: str) -> None:
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = username
        self.api_key = api_key
        self._uid: Optional[int] = None

        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    # ── Authentication ────────────────────────────────────────────────

    @property
    def uid(self) -> int:
        if self._uid is None:
            uid = self._common.authenticate(self.db, self.username, self.api_key, {})
            if not uid:
                raise PermissionError(
                    f"Odoo authentication failed for user '{self.username}'. "
                    "Check credentials and database name."
                )
            self._uid = uid
        return self._uid

    def test_connection(self) -> dict:
        """Return server version info to verify connectivity."""
        version = self._common.version()
        uid = self.uid
        return {"uid": uid, "version": version, "username": self.username}

    # ── Low-level execute ─────────────────────────────────────────────

    def execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        return self._models.execute_kw(
            self.db, self.uid, self.api_key, model, method, list(args), kwargs
        )

    # ── Common helpers ────────────────────────────────────────────────

    def search_read(
        self,
        model: str,
        domain: Optional[list] = None,
        fields: Optional[list] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[str] = None,
    ) -> list:
        kwargs: dict = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return self.execute(model, "search_read", domain or [], **kwargs)

    def search(
        self,
        model: str,
        domain: Optional[list] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[str] = None,
    ) -> list[int]:
        kwargs: dict = {}
        if limit is not None:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return self.execute(model, "search", domain or [], **kwargs)

    def read(self, model: str, ids: list[int], fields: Optional[list] = None) -> list:
        kwargs: dict = {}
        if fields is not None:
            kwargs["fields"] = fields
        return self.execute(model, "read", ids, **kwargs)

    def count(self, model: str, domain: Optional[list] = None) -> int:
        return self.execute(model, "search_count", domain or [])

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", values)

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        return self.execute(model, "write", ids, values)

    def unlink(self, model: str, ids: list[int]) -> bool:
        return self.execute(model, "unlink", ids)

    def fields_get(self, model: str, attributes: Optional[list] = None) -> dict:
        kwargs: dict = {}
        if attributes:
            kwargs["attributes"] = attributes
        return self.execute(model, "fields_get", **kwargs)

    def call(self, model: str, method: str, ids: list[int], *args: Any, **kwargs: Any) -> Any:
        """Call a model method (e.g. action_confirm) on specific records."""
        return self.execute(model, method, ids, *args, **kwargs)


# ---------------------------------------------------------------------------
# Per-request client factory
# ---------------------------------------------------------------------------

def get_client_for_request(odoo_username: Optional[str], odoo_api_key: Optional[str]) -> OdooClient:
    """
    Return an OdooClient using the credentials from the authenticated user's JWT.
    Falls back to admin credentials if no user-level credentials are present
    (e.g. client_credentials grant).
    """
    username = odoo_username or settings.odoo_admin_username
    api_key = odoo_api_key or settings.odoo_admin_api_key
    return OdooClient(username, api_key)


def validate_odoo_credentials(username: str, api_key: str) -> bool:
    """Try to authenticate against Odoo; return True on success."""
    try:
        client = OdooClient(username, api_key)
        _ = client.uid
        return True
    except Exception:
        return False
