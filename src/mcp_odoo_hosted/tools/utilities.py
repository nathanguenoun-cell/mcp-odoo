"""Utility tools: connection test, generic search."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import admin_client, user_client


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def test_connection(
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Test the connection to the Odoo instance and return server info."""
        client = user_client(odoo_username, odoo_api_key)
        return client.test_connection()

    @mcp.tool()
    def search_records(
        model: str,
        domain: Optional[list] = None,
        fields: Optional[list] = None,
        limit: int = 20,
        offset: int = 0,
        order: Optional[str] = None,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        Generic search on any Odoo model.

        Args:
            model:   Odoo model technical name, e.g. "res.partner"
            domain:  Odoo domain filter list, e.g. [["is_company", "=", True]]
            fields:  List of field names to return; if None returns all fields
            limit:   Maximum number of records (default 20)
            offset:  Pagination offset
            order:   Sort expression, e.g. "name asc"
        """
        client = user_client(odoo_username, odoo_api_key)
        return client.search_read(
            model,
            domain=domain or [],
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

    @mcp.tool()
    def get_model_fields(
        model: str,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Return the field definitions for an Odoo model."""
        client = user_client(odoo_username, odoo_api_key)
        return client.fields_get(model, attributes=["string", "type", "required", "readonly"])
