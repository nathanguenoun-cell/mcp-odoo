"""Invoice tools (account.move)."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_FIELDS = [
    "id", "name", "partner_id", "invoice_date", "invoice_date_due",
    "amount_untaxed", "amount_tax", "amount_total", "amount_residual",
    "state", "move_type", "currency_id", "invoice_line_ids", "narration",
    "payment_state",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_invoices(
        partner_id: Optional[int] = None,
        state: Optional[str] = None,
        move_type: str = "out_invoice",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        payment_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        List invoices.

        Args:
            partner_id:    Filter by customer/vendor ID
            state:         draft | posted | cancel
            move_type:     out_invoice (customer invoice), in_invoice (vendor bill),
                           out_refund, in_refund (default: out_invoice)
            date_from:     Invoice date from (YYYY-MM-DD)
            date_to:       Invoice date to (YYYY-MM-DD)
            payment_state: not_paid | in_payment | paid | partial | reversed
        """
        domain: list = [["move_type", "=", move_type]]
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        if state:
            domain.append(["state", "=", state])
        if date_from:
            domain.append(["invoice_date", ">=", date_from])
        if date_to:
            domain.append(["invoice_date", "<=", date_to])
        if payment_state:
            domain.append(["payment_state", "=", payment_state])

        client = user_client(odoo_username, odoo_api_key)
        records = client.search_read(
            "account.move",
            domain=domain,
            fields=_FIELDS,
            limit=limit,
            offset=offset,
            order="invoice_date desc",
        )
        for r in records:
            r["partner"] = r.pop("partner_id", [False, ""])[1] if r.get("partner_id") else None
            r["currency"] = r.pop("currency_id", [False, ""])[1] if r.get("currency_id") else None
        return records

    @mcp.tool()
    def get_invoice(
        invoice_id: int,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Return full details of an invoice including its lines."""
        client = user_client(odoo_username, odoo_api_key)
        records = client.read("account.move", [invoice_id], fields=_FIELDS)
        if not records:
            return {"error": f"Invoice {invoice_id} not found"}
        invoice = records[0]
        invoice["partner"] = invoice.pop("partner_id", [False, ""])[1] if invoice.get("partner_id") else None
        invoice["currency"] = invoice.pop("currency_id", [False, ""])[1] if invoice.get("currency_id") else None

        # Fetch invoice lines
        line_ids = invoice.pop("invoice_line_ids", [])
        if line_ids:
            invoice["lines"] = client.read(
                "account.move.line",
                line_ids,
                fields=["id", "name", "quantity", "price_unit", "price_subtotal", "product_id", "tax_ids"],
            )
        else:
            invoice["lines"] = []
        return invoice
