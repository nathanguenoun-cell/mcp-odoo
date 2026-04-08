"""Sales order tools (sale.order)."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_FIELDS = [
    "id", "name", "partner_id", "date_order", "amount_untaxed",
    "amount_tax", "amount_total", "state", "currency_id",
    "user_id", "note", "order_line",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_sale_orders(
        partner_id: Optional[int] = None,
        state: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """
        List sales orders.

        Args:
            partner_id: Filter by customer ID
            state:      draft | sent | sale | done | cancel
            date_from:  Order date from (YYYY-MM-DD)
            date_to:    Order date to (YYYY-MM-DD)
        """
        domain: list = []
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        if state:
            domain.append(["state", "=", state])
        if date_from:
            domain.append(["date_order", ">=", date_from])
        if date_to:
            domain.append(["date_order", "<=", date_to])

        client = user_client()
        records = client.search_read(
            "sale.order",
            domain=domain,
            fields=_FIELDS,
            limit=limit,
            offset=offset,
            order="date_order desc",
        )
        for r in records:
            r["partner"] = r.pop("partner_id", [False, ""])[1] if r.get("partner_id") else None
            r["salesperson"] = r.pop("user_id", [False, ""])[1] if r.get("user_id") else None
            r["currency"] = r.pop("currency_id", [False, ""])[1] if r.get("currency_id") else None
            r.pop("order_line", None)  # fetched separately in get_sale_order
        return records

    @mcp.tool()
    def get_sale_order(order_id: int) -> dict:
        """Return full details of a sale order including its lines."""
        client = user_client()
        records = client.read("sale.order", [order_id], fields=_FIELDS)
        if not records:
            return {"error": f"Sale order {order_id} not found"}
        order = records[0]
        order["partner"] = order.pop("partner_id", [False, ""])[1] if order.get("partner_id") else None
        order["salesperson"] = order.pop("user_id", [False, ""])[1] if order.get("user_id") else None
        order["currency"] = order.pop("currency_id", [False, ""])[1] if order.get("currency_id") else None

        line_ids = order.pop("order_line", [])
        if line_ids:
            order["lines"] = client.read(
                "sale.order.line",
                line_ids,
                fields=["id", "name", "product_id", "product_uom_qty", "price_unit", "price_subtotal", "state"],
            )
        else:
            order["lines"] = []
        return order
