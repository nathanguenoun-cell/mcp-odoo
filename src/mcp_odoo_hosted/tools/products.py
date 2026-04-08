"""Product tools (product.product / product.template)."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_TMPL_FIELDS = [
    "id", "name", "description", "list_price", "standard_price",
    "type", "uom_id", "categ_id", "active", "sale_ok", "purchase_ok",
    "taxes_id", "image_128",
]
_PROD_FIELDS = [
    "id", "name", "product_tmpl_id", "list_price", "standard_price",
    "default_code", "barcode", "active", "qty_available", "uom_id",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_products(
        search: Optional[str] = None,
        product_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        List products.

        Args:
            search:       Filter by name or reference
            product_type: consu | service | product (storable)
            limit:        Max records (default 50)
        """
        domain: list = [["active", "=", True]]
        if search:
            domain.append("|")
            domain.append(["name", "ilike", search])
            domain.append(["default_code", "ilike", search])
        if product_type:
            domain.append(["type", "=", product_type])

        client = user_client(odoo_username, odoo_api_key)
        records = client.search_read(
            "product.product",
            domain=domain,
            fields=_PROD_FIELDS,
            limit=limit,
            offset=offset,
            order="name asc",
        )
        for r in records:
            r["uom"] = r.pop("uom_id", [False, ""])[1] if r.get("uom_id") else None
        return records

    @mcp.tool()
    def get_product(
        product_id: int,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Return full details of a product variant."""
        client = user_client(odoo_username, odoo_api_key)
        records = client.read("product.product", [product_id], fields=_PROD_FIELDS)
        if not records:
            return {"error": f"Product {product_id} not found"}
        r = records[0]
        r["uom"] = r.pop("uom_id", [False, ""])[1] if r.get("uom_id") else None
        r.pop("image_128", None)  # skip binary data in default output
        return r
