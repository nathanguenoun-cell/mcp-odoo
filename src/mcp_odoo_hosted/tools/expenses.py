"""Expense tools (hr.expense)."""
from __future__ import annotations

import base64
from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_FIELDS = [
    "id", "name", "date", "employee_id", "product_id", "total_amount",
    "currency_id", "payment_mode", "state", "sheet_id", "description",
    "company_id", "quantity", "unit_amount",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_expense_categories() -> list:
        """List available expense categories (products configured as expenses)."""
        client = user_client()
        return client.search_read(
            "product.product",
            domain=[["can_be_expensed", "=", True]],
            fields=["id", "name", "standard_price", "uom_id"],
            limit=100,
            order="name asc",
        )

    @mcp.tool()
    def list_expenses(
        employee_id: Optional[int] = None,
        state: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """
        List expense records.

        Args:
            employee_id: Filter by employee ID
            state:       Filter by state: draft | reported | approved | done | refused
            date_from:   Start date (YYYY-MM-DD)
            date_to:     End date (YYYY-MM-DD)
        """
        domain: list = []
        if employee_id:
            domain.append(["employee_id", "=", employee_id])
        if state:
            domain.append(["state", "=", state])
        if date_from:
            domain.append(["date", ">=", date_from])
        if date_to:
            domain.append(["date", "<=", date_to])

        client = user_client()
        records = client.search_read(
            "hr.expense",
            domain=domain,
            fields=_FIELDS,
            limit=limit,
            offset=offset,
            order="date desc",
        )
        for r in records:
            r["employee"] = r.pop("employee_id", [False, ""])[1] if r.get("employee_id") else None
            r["category"] = r.pop("product_id", [False, ""])[1] if r.get("product_id") else None
            r["currency"] = r.pop("currency_id", [False, ""])[1] if r.get("currency_id") else None
        return records

    @mcp.tool()
    def create_expense(
        name: str,
        employee_id: int,
        product_id: int,
        total_amount: float,
        date: Optional[str] = None,
        description: Optional[str] = None,
        payment_mode: str = "own_account",
        quantity: float = 1.0,
    ) -> dict:
        """
        Create a new expense.

        Args:
            name:         Expense name / title
            employee_id:  Employee ID
            product_id:   Expense category product ID
            total_amount: Total amount
            date:         Expense date (YYYY-MM-DD), defaults to today
            payment_mode: "own_account" (employee paid) or "company_account"
            quantity:     Quantity (default 1.0)
        """
        values: dict = {
            "name": name,
            "employee_id": employee_id,
            "product_id": product_id,
            "total_amount": total_amount,
            "payment_mode": payment_mode,
            "quantity": quantity,
        }
        if date:
            values["date"] = date
        if description:
            values["description"] = description

        client = user_client()
        new_id = client.create("hr.expense", values)
        return {"id": new_id, "name": name}

    @mcp.tool()
    def update_expense(
        expense_id: int,
        name: Optional[str] = None,
        total_amount: Optional[float] = None,
        date: Optional[str] = None,
        description: Optional[str] = None,
        quantity: Optional[float] = None,
    ) -> dict:
        """Update an existing expense (only while in draft state)."""
        values: dict = {}
        if name is not None:
            values["name"] = name
        if total_amount is not None:
            values["total_amount"] = total_amount
        if date is not None:
            values["date"] = date
        if description is not None:
            values["description"] = description
        if quantity is not None:
            values["quantity"] = quantity

        if not values:
            return {"error": "No fields to update"}

        client = user_client()
        client.write("hr.expense", [expense_id], values)
        return {"id": expense_id, "updated": list(values.keys())}

    @mcp.tool()
    def delete_expense(expense_id: int) -> dict:
        """Delete a draft expense."""
        client = user_client()
        client.unlink("hr.expense", [expense_id])
        return {"id": expense_id, "deleted": True}

    @mcp.tool()
    def list_expense_attachments(expense_id: int) -> list:
        """List attachments on an expense."""
        client = user_client()
        return client.search_read(
            "ir.attachment",
            domain=[["res_model", "=", "hr.expense"], ["res_id", "=", expense_id]],
            fields=["id", "name", "mimetype", "file_size", "create_date"],
        )

    @mcp.tool()
    def add_expense_attachment(
        expense_id: int,
        filename: str,
        file_content_base64: str,
        mimetype: str = "application/octet-stream",
    ) -> dict:
        """
        Attach a file to an expense.

        Args:
            expense_id:           Expense ID
            filename:             File name (e.g. "receipt.pdf")
            file_content_base64:  Base64-encoded file content
            mimetype:             MIME type (e.g. "application/pdf")
        """
        client = user_client()
        new_id = client.create(
            "ir.attachment",
            {
                "name": filename,
                "res_model": "hr.expense",
                "res_id": expense_id,
                "datas": file_content_base64,
                "mimetype": mimetype,
            },
        )
        return {"id": new_id, "filename": filename}
