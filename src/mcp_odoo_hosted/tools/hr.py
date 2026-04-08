"""Human Resources tools (hr.employee, hr.leave, etc.)."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_EMP_FIELDS = [
    "id", "name", "job_id", "job_title", "department_id", "parent_id",
    "work_email", "work_phone", "mobile_phone", "gender",
    "birthday", "company_id", "resource_calendar_id", "active",
]


def register(mcp: FastMCP) -> None:

    # ── Employees ─────────────────────────────────────────────────────

    @mcp.tool()
    def list_employees(
        department_id: Optional[int] = None,
        search: Optional[str] = None,
        active: bool = True,
        limit: int = 100,
    ) -> list:
        """List employees."""
        domain: list = [["active", "=", active]]
        if department_id:
            domain.append(["department_id", "=", department_id])
        if search:
            domain.append(["name", "ilike", search])

        client = user_client()
        records = client.search_read(
            "hr.employee",
            domain=domain,
            fields=_EMP_FIELDS,
            limit=limit,
            order="name asc",
        )
        for r in records:
            r["department"] = r.pop("department_id", [False, ""])[1] if r.get("department_id") else None
            r["job"] = r.pop("job_id", [False, ""])[1] if r.get("job_id") else None
            r["manager"] = r.pop("parent_id", [False, ""])[1] if r.get("parent_id") else None
        return records

    @mcp.tool()
    def get_employee(employee_id: int) -> dict:
        """Return full details of an employee."""
        client = user_client()
        records = client.read("hr.employee", [employee_id], fields=_EMP_FIELDS)
        if not records:
            return {"error": f"Employee {employee_id} not found"}
        r = records[0]
        r["department"] = r.pop("department_id", [False, ""])[1] if r.get("department_id") else None
        r["job"] = r.pop("job_id", [False, ""])[1] if r.get("job_id") else None
        r["manager"] = r.pop("parent_id", [False, ""])[1] if r.get("parent_id") else None
        return r

    # ── Departments ───────────────────────────────────────────────────

    @mcp.tool()
    def list_departments(search: Optional[str] = None) -> list:
        """List HR departments."""
        domain: list = []
        if search:
            domain.append(["name", "ilike", search])
        client = user_client()
        return client.search_read(
            "hr.department",
            domain=domain,
            fields=["id", "name", "parent_id", "manager_id", "member_ids"],
            limit=100,
            order="name asc",
        )

    # ── Leave / Time-off ──────────────────────────────────────────────

    @mcp.tool()
    def list_leave_types() -> list:
        """List available leave (time-off) types."""
        client = user_client()
        return client.search_read(
            "hr.leave.type",
            domain=[["active", "=", True]],
            fields=["id", "name", "allocation_type", "requires_allocation", "leave_validation_type"],
            limit=50,
            order="name asc",
        )

    @mcp.tool()
    def list_leave_allocations(
        employee_id: Optional[int] = None,
        holiday_status_id: Optional[int] = None,
        state: Optional[str] = None,
    ) -> list:
        """
        List leave allocations.

        Args:
            employee_id:       Filter by employee ID
            holiday_status_id: Filter by leave type ID
            state:             draft | confirm | validate1 | validate | refuse
        """
        domain: list = []
        if employee_id:
            domain.append(["employee_id", "=", employee_id])
        if holiday_status_id:
            domain.append(["holiday_status_id", "=", holiday_status_id])
        if state:
            domain.append(["state", "=", state])

        client = user_client()
        return client.search_read(
            "hr.leave.allocation",
            domain=domain,
            fields=[
                "id", "employee_id", "holiday_status_id", "number_of_days",
                "state", "date_from", "date_to", "notes",
            ],
            limit=100,
        )

    @mcp.tool()
    def create_leave_allocation(
        employee_id: int,
        holiday_status_id: int,
        number_of_days: float,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Create a leave allocation for an employee.

        Args:
            employee_id:       Employee ID
            holiday_status_id: Leave type ID
            number_of_days:    Number of days to allocate
            date_from:         Validity start (YYYY-MM-DD)
            date_to:           Validity end (YYYY-MM-DD)
            notes:             Internal notes
        """
        values: dict = {
            "employee_id": employee_id,
            "holiday_status_id": holiday_status_id,
            "number_of_days": number_of_days,
        }
        if date_from:
            values["date_from"] = date_from
        if date_to:
            values["date_to"] = date_to
        if notes:
            values["notes"] = notes

        client = user_client()
        new_id = client.create("hr.leave.allocation", values)
        return {"id": new_id, "employee_id": employee_id, "days": number_of_days}

    @mcp.tool()
    def approve_leave_allocation(allocation_id: int) -> dict:
        """Approve (validate) a leave allocation."""
        client = user_client()
        client.call("hr.leave.allocation", "action_validate", [allocation_id])
        return {"id": allocation_id, "state": "validate"}

    # ── Public holidays ───────────────────────────────────────────────

    @mcp.tool()
    def list_public_holidays(
        year: Optional[int] = None,
        country_id: Optional[int] = None,
    ) -> list:
        """List public holidays."""
        domain: list = []
        if country_id:
            domain.append(["country_id", "=", country_id])

        client = user_client()
        lines = client.search_read(
            "resource.calendar.leaves",
            domain=domain,
            fields=["id", "name", "date_from", "date_to", "resource_id", "calendar_id"],
            limit=200,
            order="date_from asc",
        )
        if year:
            lines = [l for l in lines if str(year) in (l.get("date_from") or "")]
        return lines

    @mcp.tool()
    def create_public_holiday(
        name: str,
        date_from: str,
        date_to: str,
        company_id: Optional[int] = None,
    ) -> dict:
        """
        Create a global public holiday.

        Args:
            name:       Holiday name
            date_from:  Start datetime (YYYY-MM-DD HH:MM:SS)
            date_to:    End datetime (YYYY-MM-DD HH:MM:SS)
            company_id: Restrict to a specific company (None = all companies)
        """
        values: dict = {"name": name, "date_from": date_from, "date_to": date_to}
        if company_id:
            values["company_id"] = company_id

        client = user_client()
        new_id = client.create("resource.calendar.leaves", values)
        return {"id": new_id, "name": name}
