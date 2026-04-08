"""Timesheet tools (account.analytic.line)."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_FIELDS = [
    "id", "date", "name", "unit_amount", "employee_id",
    "project_id", "task_id", "account_id",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_timesheets(
        employee_id: Optional[int] = None,
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        List timesheets.

        Args:
            employee_id: Filter by employee ID
            project_id:  Filter by project ID
            task_id:     Filter by task ID
            date_from:   Start date inclusive (YYYY-MM-DD)
            date_to:     End date inclusive (YYYY-MM-DD)
            limit:       Max records
        """
        domain: list = [["project_id", "!=", False]]
        if employee_id:
            domain.append(["employee_id", "=", employee_id])
        if project_id:
            domain.append(["project_id", "=", project_id])
        if task_id:
            domain.append(["task_id", "=", task_id])
        if date_from:
            domain.append(["date", ">=", date_from])
        if date_to:
            domain.append(["date", "<=", date_to])

        client = user_client(odoo_username, odoo_api_key)
        records = client.search_read(
            "account.analytic.line",
            domain=domain,
            fields=_FIELDS,
            limit=limit,
            offset=offset,
            order="date desc",
        )
        for r in records:
            r["employee"] = r.pop("employee_id", [False, ""])[1] if r.get("employee_id") else None
            r["project"] = r.pop("project_id", [False, ""])[1] if r.get("project_id") else None
            r["task"] = r.pop("task_id", [False, ""])[1] if r.get("task_id") else None
        return records

    @mcp.tool()
    def get_timesheet_summary_by_employee(
        date_from: str,
        date_to: str,
        project_id: Optional[int] = None,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        Return total hours per employee for a date range.

        Args:
            date_from:  Start date (YYYY-MM-DD)
            date_to:    End date (YYYY-MM-DD)
            project_id: Restrict to a specific project
        """
        domain: list = [
            ["project_id", "!=", False],
            ["date", ">=", date_from],
            ["date", "<=", date_to],
        ]
        if project_id:
            domain.append(["project_id", "=", project_id])

        client = user_client(odoo_username, odoo_api_key)
        records = client.search_read(
            "account.analytic.line",
            domain=domain,
            fields=["employee_id", "unit_amount"],
            limit=None,
        )
        # Aggregate by employee
        totals: dict[str, float] = {}
        for r in records:
            emp = r["employee_id"][1] if r.get("employee_id") else "Unknown"
            totals[emp] = totals.get(emp, 0.0) + (r.get("unit_amount") or 0.0)

        return [
            {"employee": k, "total_hours": round(v, 2)}
            for k, v in sorted(totals.items())
        ]

    @mcp.tool()
    def create_timesheet(
        date: str,
        project_id: int,
        employee_id: int,
        hours: float,
        description: Optional[str] = None,
        task_id: Optional[int] = None,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """
        Create a new timesheet entry.

        Args:
            date:        Date in YYYY-MM-DD format
            project_id:  Project ID
            employee_id: Employee ID
            hours:       Number of hours
            description: Work description
            task_id:     Optional task ID
        """
        values: dict = {
            "date": date,
            "project_id": project_id,
            "employee_id": employee_id,
            "unit_amount": hours,
            "name": description or "/",
        }
        if task_id:
            values["task_id"] = task_id

        client = user_client(odoo_username, odoo_api_key)
        new_id = client.create("account.analytic.line", values)
        return {"id": new_id, "date": date, "hours": hours}

    @mcp.tool()
    def update_timesheet(
        timesheet_id: int,
        date: Optional[str] = None,
        hours: Optional[float] = None,
        description: Optional[str] = None,
        task_id: Optional[int] = None,
        project_id: Optional[int] = None,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Update an existing timesheet entry."""
        values: dict = {}
        if date is not None:
            values["date"] = date
        if hours is not None:
            values["unit_amount"] = hours
        if description is not None:
            values["name"] = description
        if task_id is not None:
            values["task_id"] = task_id
        if project_id is not None:
            values["project_id"] = project_id

        if not values:
            return {"error": "No fields to update"}

        client = user_client(odoo_username, odoo_api_key)
        client.write("account.analytic.line", [timesheet_id], values)
        return {"id": timesheet_id, "updated": list(values.keys())}

    @mcp.tool()
    def delete_timesheet(
        timesheet_id: int,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> dict:
        """Delete a timesheet entry by ID."""
        client = user_client(odoo_username, odoo_api_key)
        client.unlink("account.analytic.line", [timesheet_id])
        return {"id": timesheet_id, "deleted": True}
