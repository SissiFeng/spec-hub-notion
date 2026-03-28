"""Notion API client wrapper for Spec Hub.

Handles all HTTP communication with the Notion REST API v1, including
page/database CRUD, comments, user lookup, and search.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class NotionClient:
    """Thin async wrapper around the Notion REST API."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.environ.get("NOTION_API_TOKEN", "")
        if not self.token:
            raise ValueError(
                "NOTION_API_TOKEN is required. Set it as an environment variable "
                "or pass it to NotionClient(token=...)."
            )
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an authenticated Notion API request."""
        url = f"{NOTION_API_BASE}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.request(
                method,
                url,
                headers=self._headers,
                json=body,
                params=params,
            )
            if resp.status_code >= 400:
                detail = resp.text
                try:
                    detail = resp.json().get("message", detail)
                except Exception:
                    pass
                raise NotionAPIError(resp.status_code, detail)
            return resp.json()

    async def get(self, path: str, **kwargs: Any) -> Dict[str, Any]:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Dict[str, Any]:
        return await self._request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Dict[str, Any]:
        return await self._request("PATCH", path, **kwargs)

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    async def create_page(
        self,
        parent: Dict[str, str],
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
        icon: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a Notion page."""
        body: Dict[str, Any] = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children
        if icon:
            body["icon"] = icon
        return await self.post("pages", body=body)

    async def update_page(
        self, page_id: str, properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update page properties."""
        return await self.patch(f"pages/{page_id}", body={"properties": properties})

    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Retrieve a page by ID."""
        return await self.get(f"pages/{page_id}")

    # ------------------------------------------------------------------
    # Databases
    # ------------------------------------------------------------------

    async def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: Dict[str, Any],
        icon: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new database under a parent page."""
        body: Dict[str, Any] = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        if icon:
            body["icon"] = icon
        return await self.post("databases", body=body)

    async def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
        start_cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query a database with optional filters and sorts."""
        body: Dict[str, Any] = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor
        return await self.post(f"databases/{database_id}/query", body=body)

    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Retrieve database metadata."""
        return await self.get(f"databases/{database_id}")

    async def update_database(
        self, database_id: str, properties: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        """Update database schema."""
        body: Dict[str, Any] = {}
        if properties:
            body["properties"] = properties
        body.update(kwargs)
        return await self.patch(f"databases/{database_id}", body=body)

    # ------------------------------------------------------------------
    # Blocks (page content)
    # ------------------------------------------------------------------

    async def append_blocks(
        self, page_id: str, children: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Append block children to a page."""
        return await self.patch(
            f"blocks/{page_id}/children", body={"children": children}
        )

    async def get_block_children(
        self, block_id: str, start_cursor: Optional[str] = None, page_size: int = 100
    ) -> Dict[str, Any]:
        """Get child blocks of a page or block."""
        params: Dict[str, Any] = {"page_size": page_size}
        if start_cursor:
            params["start_cursor"] = start_cursor
        return await self.get(f"blocks/{block_id}/children", params=params)

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    async def create_comment(
        self,
        page_id: str,
        rich_text: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a comment on a page. Supports @mentions via rich_text."""
        body = {
            "parent": {"page_id": page_id},
            "rich_text": rich_text,
        }
        return await self.post("comments", body=body)

    async def get_comments(
        self, block_id: str, start_cursor: Optional[str] = None, page_size: int = 100
    ) -> Dict[str, Any]:
        """List comments on a page or block."""
        params: Dict[str, Any] = {"block_id": block_id, "page_size": page_size}
        if start_cursor:
            params["start_cursor"] = start_cursor
        return await self.get("comments", params=params)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def list_users(self, start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """List all users in the workspace."""
        params: Dict[str, Any] = {}
        if start_cursor:
            params["start_cursor"] = start_cursor
        return await self.get("users", params=params)

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get a single user by ID."""
        return await self.get(f"users/{user_id}")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str = "",
        filter_type: Optional[str] = None,
        sort_direction: str = "descending",
        page_size: int = 20,
        start_cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search across the workspace."""
        body: Dict[str, Any] = {
            "page_size": page_size,
            "sort": {"direction": sort_direction, "timestamp": "last_edited_time"},
        }
        if query:
            body["query"] = query
        if filter_type:
            body["filter"] = {"value": filter_type, "property": "object"}
        if start_cursor:
            body["start_cursor"] = start_cursor
        return await self.post("search", body=body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class NotionAPIError(Exception):
    """Raised when the Notion API returns an error."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Notion API error {status_code}: {message}")


def rich_text(content: str) -> List[Dict[str, Any]]:
    """Build a simple rich_text array from plain text."""
    return [{"type": "text", "text": {"content": content}}]


def mention_user(user_id: str) -> Dict[str, Any]:
    """Build a rich_text mention element for a Notion user."""
    return {
        "type": "mention",
        "mention": {"type": "user", "user": {"id": user_id}},
    }


def title_property(text: str) -> Dict[str, Any]:
    """Build a title property value."""
    return {"title": rich_text(text)}


def select_property(name: str) -> Dict[str, Any]:
    """Build a select property value."""
    return {"select": {"name": name}}


def multi_select_property(names: List[str]) -> Dict[str, Any]:
    """Build a multi-select property value."""
    return {"multi_select": [{"name": n} for n in names]}


def relation_property(page_ids: List[str]) -> Dict[str, Any]:
    """Build a relation property value."""
    return {"relation": [{"id": pid} for pid in page_ids]}


def rich_text_property(text: str) -> Dict[str, Any]:
    """Build a rich_text property value."""
    return {"rich_text": rich_text(text)}


def number_property(value: float) -> Dict[str, Any]:
    """Build a number property value."""
    return {"number": value}


def checkbox_property(value: bool) -> Dict[str, Any]:
    """Build a checkbox property value."""
    return {"checkbox": value}


def date_property(date_str: str) -> Dict[str, Any]:
    """Build a date property value (ISO 8601)."""
    return {"date": {"start": date_str}}


def url_property(url: str) -> Dict[str, Any]:
    """Build a URL property value."""
    return {"url": url}


def now_iso() -> str:
    """Current UTC timestamp in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Property value extractors
# ---------------------------------------------------------------------------


def extract_title(page: Dict[str, Any], prop_name: str = "Name") -> str:
    """Extract the plain text from a title property."""
    try:
        parts = page["properties"][prop_name]["title"]
        return "".join(p.get("plain_text", "") for p in parts)
    except (KeyError, IndexError):
        return ""


def extract_rich_text(page: Dict[str, Any], prop_name: str) -> str:
    """Extract plain text from a rich_text property."""
    try:
        parts = page["properties"][prop_name]["rich_text"]
        return "".join(p.get("plain_text", "") for p in parts)
    except (KeyError, IndexError):
        return ""


def extract_select(page: Dict[str, Any], prop_name: str) -> str:
    """Extract the name from a select property."""
    try:
        sel = page["properties"][prop_name]["select"]
        return sel["name"] if sel else ""
    except (KeyError, TypeError):
        return ""


def extract_multi_select(page: Dict[str, Any], prop_name: str) -> List[str]:
    """Extract names from a multi_select property."""
    try:
        return [s["name"] for s in page["properties"][prop_name]["multi_select"]]
    except (KeyError, TypeError):
        return []


def extract_number(page: Dict[str, Any], prop_name: str) -> Optional[float]:
    """Extract a number property value."""
    try:
        return page["properties"][prop_name]["number"]
    except (KeyError, TypeError):
        return None


def extract_checkbox(page: Dict[str, Any], prop_name: str) -> bool:
    """Extract a checkbox property value."""
    try:
        return page["properties"][prop_name]["checkbox"]
    except (KeyError, TypeError):
        return False


def extract_relation_ids(page: Dict[str, Any], prop_name: str) -> List[str]:
    """Extract related page IDs from a relation property."""
    try:
        return [r["id"] for r in page["properties"][prop_name]["relation"]]
    except (KeyError, TypeError):
        return []


def extract_date(page: Dict[str, Any], prop_name: str) -> str:
    """Extract date string from a date property."""
    try:
        d = page["properties"][prop_name]["date"]
        return d["start"] if d else ""
    except (KeyError, TypeError):
        return ""


def extract_created_time(page: Dict[str, Any]) -> str:
    """Extract created_time from page metadata."""
    return page.get("created_time", "")


def extract_last_edited_time(page: Dict[str, Any]) -> str:
    """Extract last_edited_time from page metadata."""
    return page.get("last_edited_time", "")


def extract_page_id(page: Dict[str, Any]) -> str:
    """Extract page ID."""
    return page.get("id", "")
