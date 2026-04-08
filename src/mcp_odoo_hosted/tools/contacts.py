"""Contact (res.partner) tools."""
from __future__ import annotations

from typing import Optional
from mcp.server.fastmcp import FastMCP

from ._base import user_client

_FIELDS = [
    "id", "name", "email", "phone", "mobile", "website",
    "street", "city", "zip", "country_id", "state_id",
    "is_company", "parent_id", "comment", "active",
    "customer_rank", "supplier_rank",
]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_contacts(
        search: Optional[str] = None,
        is_company: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """
        List contacts / partners.

        Args:
            search:     Filter by name or email (case-insensitive)
            is_company: True = companies only, False = individuals only, None = all
            limit:      Max records to return (default 50)
            offset:     Pagination offset
        """
        domain: list = [["active", "=", True]]
        if search:
            domain.append("|")
            domain.append(["name", "ilike", search])
            domain.append(["email", "ilike", search])
        if is_company is not None:
            domain.append(["is_company", "=", is_company])

        client = user_client()
        records = client.search_read(
            "res.partner", domain=domain, fields=_FIELDS, limit=limit, offset=offset, order="name asc"
        )
        # Flatten Many2one fields
        for r in records:
            r["country"] = r.pop("country_id", [False, ""])[1] if r.get("country_id") else None
            r["parent"] = r.pop("parent_id", [False, ""])[1] if r.get("parent_id") else None
        return records

    @mcp.tool()
    def get_contact(
        contact_id: int,
    ) -> dict:
        """Return full details for a contact by ID."""
        client = user_client()
        records = client.read("res.partner", [contact_id], fields=_FIELDS)
        if not records:
            return {"error": f"Contact {contact_id} not found"}
        r = records[0]
        r["country"] = r.pop("country_id", [False, ""])[1] if r.get("country_id") else None
        r["parent"] = r.pop("parent_id", [False, ""])[1] if r.get("parent_id") else None
        return r

    @mcp.tool()
    def create_contact(
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        mobile: Optional[str] = None,
        is_company: bool = False,
        street: Optional[str] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        country_id: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> dict:
        """Create a new contact / partner."""
        values: dict = {"name": name, "is_company": is_company}
        if email:
            values["email"] = email
        if phone:
            values["phone"] = phone
        if mobile:
            values["mobile"] = mobile
        if street:
            values["street"] = street
        if city:
            values["city"] = city
        if zip_code:
            values["zip"] = zip_code
        if country_id:
            values["country_id"] = country_id
        if comment:
            values["comment"] = comment

        client = user_client()
        new_id = client.create("res.partner", values)
        return {"id": new_id, "name": name}

    @mcp.tool()
    def update_contact(
        contact_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        mobile: Optional[str] = None,
        street: Optional[str] = None,
        city: Optional[str] = None,
        zip_code: Optional[str] = None,
        country_id: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> dict:
        """Update an existing contact."""
        values: dict = {}
        if name is not None:
            values["name"] = name
        if email is not None:
            values["email"] = email
        if phone is not None:
            values["phone"] = phone
        if mobile is not None:
            values["mobile"] = mobile
        if street is not None:
            values["street"] = street
        if city is not None:
            values["city"] = city
        if zip_code is not None:
            values["zip"] = zip_code
        if country_id is not None:
            values["country_id"] = country_id
        if comment is not None:
            values["comment"] = comment

        if not values:
            return {"error": "No fields to update"}

        client = user_client()
        client.write("res.partner", [contact_id], values)
        return {"id": contact_id, "updated": list(values.keys())}
