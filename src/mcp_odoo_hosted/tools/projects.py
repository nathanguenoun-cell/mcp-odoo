"""Project and task tools."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_projects(
        search: Optional[str] = None,
        limit: int = 50,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """List projects the user has access to."""
        domain: list = []
        if search:
            domain.append(["name", "ilike", search])
        client = user_client(odoo_username, odoo_api_key)
        return client.search_read(
            "project.project",
            domain=domain,
            fields=["id", "name", "partner_id", "user_id", "date_start", "date", "description"],
            limit=limit,
            order="name asc",
        )

    @mcp.tool()
    def list_tasks(
        project_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        search: Optional[str] = None,
        stage: Optional[str] = None,
        limit: int = 50,
        odoo_username: Optional[str] = None,
        odoo_api_key: Optional[str] = None,
    ) -> list:
        """
        List tasks, optionally filtered by project, assignee, or name search.

        Args:
            project_id:  Filter by project ID
            assignee_id: Filter by assigned user ID
            search:      Filter by task name
            stage:       Filter by stage name (e.g. "In Progress")
            limit:       Max records (default 50)
        """
        domain: list = []
        if project_id:
            domain.append(["project_id", "=", project_id])
        if assignee_id:
            domain.append(["user_ids", "in", [assignee_id]])
        if search:
            domain.append(["name", "ilike", search])
        if stage:
            domain.append(["stage_id.name", "ilike", stage])

        client = user_client(odoo_username, odoo_api_key)
        records = client.search_read(
            "project.task",
            domain=domain,
            fields=[
                "id", "name", "project_id", "user_ids", "stage_id",
                "priority", "date_deadline", "description", "tag_ids",
            ],
            limit=limit,
            order="priority desc, date_deadline asc",
        )
        for r in records:
            r["project"] = r.pop("project_id", [False, ""])[1] if r.get("project_id") else None
            r["stage"] = r.pop("stage_id", [False, ""])[1] if r.get("stage_id") else None
        return records
