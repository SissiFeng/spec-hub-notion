#!/usr/bin/env python3
"""Spec Hub for Notion — MCP Server.

An engineering spec management system that uses Notion as the data layer.
Provides tools for managing specs, change requests, decisions, bugs, and
audit trails — all stored in structured Notion databases with full
traceability, @mention support, and cross-linking.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP

from spec_hub_notion.models import (
    ApproveVersionInput,
    CreateChangeRequestInput,
    CreateImpactLinkInput,
    CreateProjectInput,
    CreateSpecInput,
    CreateSpecVersionInput,
    FileBugInput,
    GetOverviewInput,
    GetSpecInput,
    GetTimelineInput,
    ListBugsInput,
    ListChangeRequestsInput,
    ListProjectsInput,
    ListSpecsInput,
    ListUsersInput,
    LogDecisionInput,
    ResponseFormat,
    SearchInput,
    UpdateBugInput,
    UpdateChangeRequestInput,
)
from spec_hub_notion.notion_client import (
    NotionAPIError,
    NotionClient,
    checkbox_property,
    date_property,
    extract_checkbox,
    extract_created_time,
    extract_date,
    extract_multi_select,
    extract_number,
    extract_page_id,
    extract_relation_ids,
    extract_rich_text,
    extract_select,
    extract_title,
    mention_user,
    multi_select_property,
    now_iso,
    number_property,
    relation_property,
    rich_text,
    rich_text_property,
    select_property,
    title_property,
)

# ---------------------------------------------------------------------------
# Database ID storage (persisted per workspace via config page)
# ---------------------------------------------------------------------------

# These are populated by setup_workspace or loaded from env
_db_ids: Dict[str, str] = {}

DB_KEYS = [
    "projects",
    "spec_items",
    "spec_versions",
    "change_requests",
    "decision_logs",
    "bugs",
]


def _get_db_id(key: str) -> str:
    """Get a database ID, falling back to environment variables."""
    if key in _db_ids:
        return _db_ids[key]
    env_key = f"SPECHUB_DB_{key.upper()}"
    val = os.environ.get(env_key, "")
    if val:
        _db_ids[key] = val
        return val
    raise ValueError(
        f"Database '{key}' not found. Run spechub_setup_workspace first, "
        f"or set {env_key} environment variable."
    )


# ---------------------------------------------------------------------------
# Lifespan — initialise Notion client
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan():
    """Initialise shared resources."""
    client = NotionClient()
    yield {"notion": client}


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "spec_hub_notion_mcp",
    lifespan=app_lifespan,
)


def _notion(ctx: Context) -> NotionClient:
    """Get the Notion client from context."""
    return ctx.request_context.lifespan_state["notion"]


def _handle_error(e: Exception) -> str:
    """Format errors consistently."""
    if isinstance(e, NotionAPIError):
        if e.status_code == 404:
            return f"Error: Resource not found — {e.message}. Check the page/database ID."
        if e.status_code == 403:
            return f"Error: Permission denied — {e.message}. Ensure the integration has access."
        if e.status_code == 429:
            return "Error: Rate limit exceeded. Wait a moment and retry."
        return f"Error: Notion API {e.status_code} — {e.message}"
    if isinstance(e, ValueError):
        return f"Error: {e}"
    return f"Error: {type(e).__name__} — {e}"


# ===================================================================
# TOOL 1: Setup Workspace
# ===================================================================


@mcp.tool(
    name="spechub_setup_workspace",
    annotations={
        "title": "Setup Spec Hub Workspace",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_setup_workspace(
    parent_page_id: str, ctx: Context
) -> str:
    """Create all Spec Hub databases in a Notion page.

    This initialises the full workspace structure: Projects, Spec Items,
    Spec Versions, Change Requests, Decision Logs, and Bugs databases
    with proper schemas, relations, and select options.

    Run this ONCE per workspace. After setup, the database IDs are stored
    in memory for the session. For persistence across sessions, save the
    returned IDs as environment variables (SPECHUB_DB_PROJECTS, etc.).

    Args:
        parent_page_id: Notion page ID to create databases under.

    Returns:
        str: JSON with all created database IDs, or an error message.    """
    notion = _notion(ctx)
    created: Dict[str, str] = {}

    try:
        # 1. Projects Database
        db = await notion.create_database(
            parent_page_id,
            "📋 Spec Hub — Projects",
            {
                "Name": {"title": {}},
                "Description": {"rich_text": {}},
                "Owner": {"rich_text": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "active", "color": "green"},
                            {"name": "paused", "color": "yellow"},
                            {"name": "archived", "color": "gray"},
                        ]
                    }
                },
            },
            icon={"type": "emoji", "emoji": "📋"},
        )
        created["projects"] = db["id"]

        # 2. Spec Items Database
        db = await notion.create_database(
            parent_page_id,
            "📐 Spec Hub — Spec Items",
            {
                "Name": {"title": {}},
                "Type": {
                    "select": {
                        "options": [
                            {"name": t, "color": c}
                            for t, c in [
                                ("dashboard", "blue"),
                                ("page", "purple"),
                                ("component", "pink"),
                                ("kpi", "green"),
                                ("parameter", "yellow"),
                                ("metric_formula", "orange"),
                                ("api_contract", "red"),
                                ("experiment_label", "gray"),
                                ("alert_rule", "brown"),
                            ]
                        ]
                    }
                },
                "Owner": {"rich_text": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "draft", "color": "gray"},
                            {"name": "active", "color": "green"},
                            {"name": "review", "color": "yellow"},
                            {"name": "deprecated", "color": "red"},
                        ]
                    }
                },
                "Tags": {"multi_select": {"options": []}},
                "Summary": {"rich_text": {}},
                "Current Version": {"number": {"format": "number"}},
                "Project": {"relation": {"database_id": created["projects"]}},
            },
            icon={"type": "emoji", "emoji": "📐"},
        )
        created["spec_items"] = db["id"]

        # 3. Spec Versions Database
        db = await notion.create_database(
            parent_page_id,
            "📝 Spec Hub — Spec Versions",
            {
                "Name": {"title": {}},
                "Version": {"number": {"format": "number"}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "draft", "color": "gray"},
                            {"name": "under_review", "color": "yellow"},
                            {"name": "approved", "color": "green"},
                            {"name": "deprecated", "color": "red"},
                        ]
                    }
                },
                "Change Type": {
                    "select": {
                        "options": [
                            {"name": "add", "color": "green"},
                            {"name": "modify", "color": "blue"},
                            {"name": "deprecate", "color": "red"},
                        ]
                    }
                },
                "Summary": {"rich_text": {}},
                "Rationale": {"rich_text": {}},
                "Proposed By": {"rich_text": {}},
                "Approved By": {"rich_text": {}},
                "Is Current": {"checkbox": {}},
                "Spec Item": {"relation": {"database_id": created["spec_items"]}},
            },
            icon={"type": "emoji", "emoji": "📝"},
        )
        created["spec_versions"] = db["id"]

        # 4. Change Requests Database
        db = await notion.create_database(
            parent_page_id,
            "🔄 Spec Hub — Change Requests",
            {
                "Title": {"title": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": s, "color": c}
                            for s, c in [
                                ("proposed", "gray"),
                                ("under_review", "yellow"),
                                ("approved", "green"),
                                ("implementing", "blue"),
                                ("verified", "purple"),
                                ("closed", "default"),
                                ("rejected", "red"),                                ("archived", "brown"),
                            ]
                        ]
                    }
                },
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "low", "color": "gray"},
                            {"name": "medium", "color": "yellow"},
                            {"name": "high", "color": "orange"},
                            {"name": "critical", "color": "red"},
                        ]
                    }
                },
                "Requested By": {"rich_text": {}},
                "Reason": {"rich_text": {}},
                "Proposed Change": {"rich_text": {}},
                "Impact Summary": {"rich_text": {}},
                "Affects Existing Results": {"checkbox": {}},
                "Needs Frontend Sync": {"checkbox": {}},
                "Needs Backend Sync": {"checkbox": {}},
                "Needs Scientist Review": {"checkbox": {}},
                "Project": {"relation": {"database_id": created["projects"]}},
                "Linked Specs": {"relation": {"database_id": created["spec_items"]}},
            },
            icon={"type": "emoji", "emoji": "🔄"},
        )
        created["change_requests"] = db["id"]

        # 5. Decision Logs Database
        db = await notion.create_database(
            parent_page_id,
            "⚖️ Spec Hub — Decision Logs",
            {
                "Decision": {"title": {}},
                "Reason": {"rich_text": {}},
                "Decided By": {"rich_text": {}},
                "Participants": {"rich_text": {}},
                "Alternatives Considered": {"rich_text": {}},
                "Change Request": {
                    "relation": {"database_id": created["change_requests"]}
                },
            },
            icon={"type": "emoji", "emoji": "⚖️"},
        )
        created["decision_logs"] = db["id"]

        # 6. Bugs Database
        db = await notion.create_database(
            parent_page_id,
            "🐛 Spec Hub — Bugs",
            {
                "Title": {"title": {}},
                "Severity": {
                    "select": {
                        "options": [
                            {"name": "low", "color": "gray"},
                            {"name": "medium", "color": "yellow"},
                            {"name": "high", "color": "orange"},
                            {"name": "critical", "color": "red"},
                        ]
                    }
                },
                "Status": {
                    "select": {
                        "options": [
                            {"name": s, "color": c}
                            for s, c in [
                                ("open", "red"),
                                ("investigating", "yellow"),
                                ("fix_in_progress", "blue"),
                                ("resolved", "green"),
                                ("closed", "gray"),
                                ("wont_fix", "brown"),
                            ]
                        ]
                    }
                },
                "Reporter": {"rich_text": {}},
                "Assignee": {"people": {}},
                "Description": {"rich_text": {}},
                "Expected Behavior": {"rich_text": {}},
                "Actual Behavior": {"rich_text": {}},
                "Project": {"relation": {"database_id": created["projects"]}},
                "Linked Specs": {"relation": {"database_id": created["spec_items"]}},
            },
            icon={"type": "emoji", "emoji": "🐛"},
        )
        created["bugs"] = db["id"]

        # Store in memory
        _db_ids.update(created)

        return json.dumps(
            {
                "status": "success",
                "message": "Spec Hub workspace created successfully!",
                "databases": created,
                "hint": "Save these IDs as env vars for persistence: "
                + ", ".join(f"SPECHUB_DB_{k.upper()}={v}" for k, v in created.items()),
            },
            indent=2,
        )

    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 2: Create Project
# ===================================================================


@mcp.tool(
    name="spechub_create_project",
    annotations={
        "title": "Create Project",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_create_project(params: CreateProjectInput, ctx: Context) -> str:
    """Create a new project in the Spec Hub Projects database.

    A project groups related spec items, change requests, and bugs.

    Args:
        params: Project details (name, description, owner, status).

    Returns:        str: JSON with the created project page ID and details.
    """
    try:
        notion = _notion(ctx)
        db_id = _get_db_id("projects")

        page = await notion.create_page(
            parent={"database_id": db_id},
            properties={
                "Name": title_property(params.name),
                "Description": rich_text_property(params.description),
                "Owner": rich_text_property(params.owner),
                "Status": select_property(params.status),
            },
            icon={"type": "emoji", "emoji": "📁"},
        )

        return json.dumps(
            {
                "status": "success",
                "project_id": page["id"],
                "name": params.name,
                "url": page.get("url", ""),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 3: List Projects
# ===================================================================


@mcp.tool(
    name="spechub_list_projects",
    annotations={
        "title": "List Projects",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_list_projects(params: ListProjectsInput, ctx: Context) -> str:
    """List all projects in the Spec Hub workspace.

    Args:
        params: Optional filters (status) and output format.

    Returns:
        str: List of projects in the requested format.
    """
    try:
        notion = _notion(ctx)
        db_id = _get_db_id("projects")

        filter_obj = None
        if params.status:
            filter_obj = {
                "property": "Status",
                "select": {"equals": params.status},
            }

        result = await notion.query_database(db_id, filter_obj=filter_obj)
        pages = result.get("results", [])

        projects = []
        for p in pages:
            projects.append(
                {
                    "id": extract_page_id(p),
                    "name": extract_title(p),
                    "description": extract_rich_text(p, "Description"),
                    "owner": extract_rich_text(p, "Owner"),
                    "status": extract_select(p, "Status"),
                    "created": extract_created_time(p),
                }
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(projects), "projects": projects}, indent=2)

        # Markdown
        if not projects:
            return "No projects found."
        lines = [f"# Spec Hub Projects ({len(projects)})\n"]
        for proj in projects:
            status_emoji = {"active": "🟢", "paused": "🟡", "archived": "⭕"}.get(
                proj["status"], "⚪"
            )
            lines.append(f"## {status_emoji} {proj['name']}")
            lines.append(f"- **Owner**: {proj['owner']}")
            lines.append(f"- **Status**: {proj['status']}")
            if proj["description"]:
                lines.append(f"- **Description**: {proj['description']}")
            lines.append(f"- **ID**: `{proj['id']}`")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 4: Create Spec Item
# ===================================================================


async def _find_project_id(notion: NotionClient, project_name: str) -> str:
    """Look up a project page ID by name."""
    db_id = _get_db_id("projects")
    result = await notion.query_database(
        db_id,
        filter_obj={"property": "Name", "title": {"equals": project_name}},
    )
    pages = result.get("results", [])
    if not pages:
        raise ValueError(f"Project '{project_name}' not found.")
    return pages[0]["id"]


async def _find_spec_ids_by_names(
    notion: NotionClient, names: List[str]
) -> List[str]:
    """Look up spec item page IDs by names."""
    if not names:
        return []
    db_id = _get_db_id("spec_items")
    ids = []
    for name in names:
        result = await notion.query_database(
            db_id,
            filter_obj={"property": "Name", "title": {"equals": name}},
        )
        pages = result.get("results", [])
        if pages:
            ids.append(pages[0]["id"])
    return ids


@mcp.tool(
    name="spechub_create_spec",
    annotations={
        "title": "Create Spec Item",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_create_spec(params: CreateSpecInput, ctx: Context) -> str:
    """Create a new spec item linked to a project.

    A spec item represents a single trackable specification — a KPI,
    component, API contract, parameter, etc. The initial content is    stored as the first version (v1) automatically.

    Args:
        params: Spec details including project_name, type, owner, content_json.

    Returns:
        str: JSON with created spec and version IDs.
    """
    try:
        notion = _notion(ctx)
        project_id = await _find_project_id(notion, params.project_name)

        # Create the spec item
        properties: Dict[str, Any] = {
            "Name": title_property(params.name),
            "Type": select_property(params.type.value),
            "Owner": rich_text_property(params.owner),
            "Status": select_property(params.status.value),
            "Summary": rich_text_property(params.summary),
            "Current Version": number_property(1),
            "Project": relation_property([project_id]),
        }
        if params.tags:
            properties["Tags"] = multi_select_property(params.tags)

        spec_page = await notion.create_page(
            parent={"database_id": _get_db_id("spec_items")},
            properties=properties,
            icon={"type": "emoji", "emoji": "📐"},
        )
        spec_id = spec_page["id"]

        # Auto-create v1
        version_page = await notion.create_page(
            parent={"database_id": _get_db_id("spec_versions")},
            properties={
                "Name": title_property(f"{params.name} v1"),
                "Version": number_property(1),
                "Status": select_property("approved"),
                "Change Type": select_property("add"),
                "Summary": rich_text_property(params.summary or "Initial version"),
                "Proposed By": rich_text_property(params.owner),
                "Approved By": rich_text_property(params.owner),
                "Is Current": checkbox_property(True),
                "Spec Item": relation_property([spec_id]),
            },
        )

        # Store content_json as page content blocks
        if params.content_json and params.content_json != "{}":
            await notion.append_blocks(
                version_page["id"],
                [
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": rich_text(params.content_json),
                            "language": "json",
                        },
                    }
                ],
            )

        return json.dumps(
            {
                "status": "success",
                "spec_id": spec_id,
                "version_id": version_page["id"],
                "name": params.name,
                "version": 1,
                "url": spec_page.get("url", ""),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 5: List Spec Items
# ===================================================================


@mcp.tool(
    name="spechub_list_specs",
    annotations={
        "title": "List Spec Items",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_list_specs(params: ListSpecsInput, ctx: Context) -> str:
    """List and filter spec items across all projects.

    Supports filtering by project, type, status, owner, and free-text search.

    Args:
        params: Filters and output format.

    Returns:
        str: List of spec items in the requested format.
    """
    try:
        notion = _notion(ctx)
        db_id = _get_db_id("spec_items")

        filters: List[Dict[str, Any]] = []
        if params.type:
            filters.append({"property": "Type", "select": {"equals": params.type.value}})
        if params.status:
            filters.append({"property": "Status", "select": {"equals": params.status.value}})
        if params.owner:
            filters.append({"property": "Owner", "rich_text": {"contains": params.owner}})

        filter_obj = None
        if len(filters) == 1:
            filter_obj = filters[0]
        elif len(filters) > 1:
            filter_obj = {"and": filters}

        result = await notion.query_database(db_id, filter_obj=filter_obj)
        pages = result.get("results", [])

        specs = []
        for p in pages:
            name = extract_title(p)
            if params.query and params.query.lower() not in name.lower():
                continue
            specs.append(
                {
                    "id": extract_page_id(p),
                    "name": name,
                    "type": extract_select(p, "Type"),
                    "owner": extract_rich_text(p, "Owner"),
                    "status": extract_select(p, "Status"),
                    "tags": extract_multi_select(p, "Tags"),
                    "summary": extract_rich_text(p, "Summary"),
                    "current_version": extract_number(p, "Current Version"),                }
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(specs), "specs": specs}, indent=2)

        if not specs:
            return "No spec items found matching the criteria."
        lines = [f"# Spec Items ({len(specs)})\n"]
        type_emoji = {
            "kpi": "📊", "component": "🧩", "api_contract": "🔌",
            "parameter": "⚙️", "dashboard": "📈", "page": "📄",
            "metric_formula": "🔢", "experiment_label": "🧪", "alert_rule": "🚨",
        }
        for s in specs:
            emoji = type_emoji.get(s["type"], "📐")
            lines.append(f"### {emoji} {s['name']}")
            lines.append(f"- **Type**: {s['type']} | **Status**: {s['status']} | **Owner**: {s['owner']}")
            if s["tags"]:
                lines.append(f"- **Tags**: {', '.join(s['tags'])}")
            if s["summary"]:
                lines.append(f"- {s['summary']}")
            lines.append(f"- **Version**: v{int(s['current_version'] or 1)} | **ID**: `{s['id']}`")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 6: Get Spec Detail
# ===================================================================


@mcp.tool(
    name="spechub_get_spec",
    annotations={
        "title": "Get Spec Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_get_spec(params: GetSpecInput, ctx: Context) -> str:
    """Get detailed information about a spec item, including all versions.

    Retrieves the spec item properties, all its versions (with content),
    linked change requests, and related decision logs.

    Args:
        params: spec_page_id and response format.

    Returns:
        str: Detailed spec information with version history.
    """
    try:
        notion = _notion(ctx)
        page = await notion.get_page(params.spec_page_id)

        spec = {
            "id": extract_page_id(page),
            "name": extract_title(page),
            "type": extract_select(page, "Type"),
            "owner": extract_rich_text(page, "Owner"),
            "status": extract_select(page, "Status"),
            "tags": extract_multi_select(page, "Tags"),
            "summary": extract_rich_text(page, "Summary"),
            "current_version": extract_number(page, "Current Version"),
        }

        # Fetch versions
        versions_db = _get_db_id("spec_versions")
        ver_result = await notion.query_database(
            versions_db,
            filter_obj={
                "property": "Spec Item",
                "relation": {"contains": params.spec_page_id},
            },
            sorts=[{"property": "Version", "direction": "descending"}],
        )
        versions = []
        for v in ver_result.get("results", []):
            ver_data = {
                "id": extract_page_id(v),
                "version": extract_number(v, "Version"),
                "status": extract_select(v, "Status"),
                "change_type": extract_select(v, "Change Type"),
                "summary": extract_rich_text(v, "Summary"),
                "rationale": extract_rich_text(v, "Rationale"),
                "proposed_by": extract_rich_text(v, "Proposed By"),
                "approved_by": extract_rich_text(v, "Approved By"),
                "is_current": extract_checkbox(v, "Is Current"),
                "created": extract_created_time(v),
            }
            versions.append(ver_data)

        # Fetch linked change requests
        cr_db = _get_db_id("change_requests")
        cr_result = await notion.query_database(
            cr_db,
            filter_obj={
                "property": "Linked Specs",
                "relation": {"contains": params.spec_page_id},
            },
        )
        change_requests = []
        for cr in cr_result.get("results", []):
            change_requests.append(
                {
                    "id": extract_page_id(cr),
                    "title": extract_title(cr, "Title"),
                    "status": extract_select(cr, "Status"),
                    "priority": extract_select(cr, "Priority"),
                    "requested_by": extract_rich_text(cr, "Requested By"),
                }
            )

        result = {**spec, "versions": versions, "change_requests": change_requests}

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)

        # Markdown
        lines = [f"# 📐 {spec['name']}\n"]
        lines.append(f"**Type**: {spec['type']} | **Status**: {spec['status']} | **Owner**: {spec['owner']}")
        if spec["tags"]:
            lines.append(f"**Tags**: {', '.join(spec['tags'])}")
        if spec["summary"]:
            lines.append(f"\n> {spec['summary']}\n")
        lines.append(f"\n## Version History ({len(versions)} versions)\n")
        for v in versions:
            current = " ⭐ CURRENT" if v["is_current"] else ""
            lines.append(f"### v{int(v['version'] or 0)} — {v['status']}{current}")
            lines.append(f"- **Change**: {v['change_type']} | **By**: {v['proposed_by']}")
            if v["approved_by"]:
                lines.append(f"- **Approved by**: {v['approved_by']}")
            lines.append(f"- **Summary**: {v['summary']}")
            if v["rationale"]:
                lines.append(f"- **Rationale**: {v['rationale']}")
            lines.append("")

        if change_requests:
            lines.append(f"\n## Linked Change Requests ({len(change_requests)})\n")
            for cr in change_requests:
                lines.append(f"- **{cr['title']}** [{cr['status']}] (Priority: {cr['priority']}) — by {cr['requested_by']}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 7: Create Spec Version
# ===================================================================


@mcp.tool(
    name="spechub_create_spec_version",
    annotations={
        "title": "Create Spec Version",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_create_spec_version(
    params: CreateSpecVersionInput, ctx: Context
) -> str:
    """Create a new version of a spec item.

    This adds a new version entry linked to the spec. The previous
    current version is NOT automatically deprecated — use
    spechub_approve_version to promote a version and update the spec.

    Args:
        params: Version details including content_json, summary, rationale.

    Returns:
        str: JSON with the created version page ID.
    """
    try:
        notion = _notion(ctx)

        version_page = await notion.create_page(
            parent={"database_id": _get_db_id("spec_versions")},
            properties={
                "Name": title_property(
                    f"{extract_title(await notion.get_page(params.spec_page_id))} v{params.version_number}"
                ),
                "Version": number_property(params.version_number),
                "Status": select_property("draft"),
                "Change Type": select_property(params.change_type.value),
                "Summary": rich_text_property(params.summary),
                "Rationale": rich_text_property(params.rationale),
                "Proposed By": rich_text_property(params.proposed_by),
                "Is Current": checkbox_property(False),
                "Spec Item": relation_property([params.spec_page_id]),
            },
        )

        # Store content_json as code block
        if params.content_json:
            await notion.append_blocks(
                version_page["id"],
                [
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": rich_text(params.content_json),
                            "language": "json",
                        },
                    }
                ],
            )

        return json.dumps(
            {
                "status": "success",
                "version_id": version_page["id"],
                "version_number": params.version_number,
                "spec_page_id": params.spec_page_id,
                "url": version_page.get("url", ""),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 8: Approve Version
# ===================================================================


@mcp.tool(
    name="spechub_approve_version",
    annotations={
        "title": "Approve Spec Version",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_approve_version(params: ApproveVersionInput, ctx: Context) -> str:
    """Approve a spec version, making it the current version.

    This marks the version as approved and current, deprecates any
    previously current version, and updates the parent spec item's
    current version number.

    Args:
        params: version_page_id and approved_by.

    Returns:
        str: Confirmation with updated version details.
    """
    try:
        notion = _notion(ctx)

        # Get the version to find its spec item and version number
        ver_page = await notion.get_page(params.version_page_id)
        ver_num = extract_number(ver_page, "Version")
        spec_ids = extract_relation_ids(ver_page, "Spec Item")

        if not spec_ids:
            return "Error: This version is not linked to a spec item."
        spec_id = spec_ids[0]

        # Deprecate previous current versions
        versions_db = _get_db_id("spec_versions")
        old_versions = await notion.query_database(
            versions_db,
            filter_obj={
                "and": [
                    {"property": "Spec Item", "relation": {"contains": spec_id}},
                    {"property": "Is Current", "checkbox": {"equals": True}},
                ]
            },
        )
        for old_v in old_versions.get("results", []):
            if old_v["id"] != params.version_page_id:
                await notion.update_page(
                    old_v["id"],
                    {
                        "Is Current": checkbox_property(False),
                        "Status": select_property("deprecated"),
                    },
                )

        # Approve the new version
        await notion.update_page(
            params.version_page_id,
            {
                "Status": select_property("approved"),
                "Is Current": checkbox_property(True),
                "Approved By": rich_text_property(params.approved_by),
            },
        )

        # Update the spec item's current version number
        await notion.update_page(
            spec_id,
            {"Current Version": number_property(ver_num or 1)},
        )

        return json.dumps(
            {
                "status": "success",
                "message": f"Version v{int(ver_num or 1)} approved by {params.approved_by}",
                "version_id": params.version_page_id,
                "spec_id": spec_id,
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 9: Create Change Request
# ===================================================================


@mcp.tool(
    name="spechub_create_change_request",
    annotations={
        "title": "Create Change Request",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_create_change_request(
    params: CreateChangeRequestInput, ctx: Context
) -> str:
    """Create a change request linked to a project and spec items.

    Change requests track proposed changes across multiple specs, with
    impact flags indicating which teams need to sync (frontend, backend,
    scientist review). They follow a kanban workflow from proposed → closed.

    Args:
        params: CR details including title, reason, linked specs, impact flags.

    Returns:
        str: JSON with the created CR page ID.
    """
    try:
        notion = _notion(ctx)
        project_id = await _find_project_id(notion, params.project_name)
        spec_ids = await _find_spec_ids_by_names(notion, params.linked_spec_names)

        properties: Dict[str, Any] = {
            "Title": title_property(params.title),
            "Status": select_property("proposed"),
            "Priority": select_property(params.priority.value),
            "Requested By": rich_text_property(params.requested_by),
            "Reason": rich_text_property(params.reason),
            "Proposed Change": rich_text_property(params.proposed_change),
            "Impact Summary": rich_text_property(params.impact_summary),
            "Affects Existing Results": checkbox_property(params.affects_existing_results),
            "Needs Frontend Sync": checkbox_property(params.needs_frontend_sync),
            "Needs Backend Sync": checkbox_property(params.needs_backend_sync),
            "Needs Scientist Review": checkbox_property(params.needs_scientist_review),
            "Project": relation_property([project_id]),
        }
        if spec_ids:
            properties["Linked Specs"] = relation_property(spec_ids)

        # Build page content with description
        children = []
        if params.description:
            children.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": rich_text("Description")},
                }
            )
            children.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text(params.description)},
                }
            )

        cr_page = await notion.create_page(
            parent={"database_id": _get_db_id("change_requests")},
            properties=properties,
            children=children if children else None,
            icon={"type": "emoji", "emoji": "🔄"},
        )

        return json.dumps(
            {
                "status": "success",
                "cr_id": cr_page["id"],
                "title": params.title,
                "linked_specs": len(spec_ids),
                "url": cr_page.get("url", ""),
            },
            indent=2,
        )    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 10: List Change Requests
# ===================================================================


@mcp.tool(
    name="spechub_list_change_requests",
    annotations={
        "title": "List Change Requests",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_list_change_requests(
    params: ListChangeRequestsInput, ctx: Context
) -> str:
    """List change requests with optional filters.

    Returns CRs grouped by status (kanban-style) in markdown, or as a
    flat list in JSON.

    Args:
        params: Filters (project, status, priority) and output format.

    Returns:
        str: Change requests list.
    """
    try:
        notion = _notion(ctx)
        db_id = _get_db_id("change_requests")

        filters: List[Dict[str, Any]] = []
        if params.status:
            filters.append({"property": "Status", "select": {"equals": params.status.value}})
        if params.priority:
            filters.append({"property": "Priority", "select": {"equals": params.priority.value}})

        filter_obj = None
        if len(filters) == 1:
            filter_obj = filters[0]
        elif len(filters) > 1:
            filter_obj = {"and": filters}

        result = await notion.query_database(db_id, filter_obj=filter_obj)
        pages = result.get("results", [])

        crs = []
        for p in pages:
            crs.append(
                {
                    "id": extract_page_id(p),
                    "title": extract_title(p, "Title"),
                    "status": extract_select(p, "Status"),
                    "priority": extract_select(p, "Priority"),
                    "requested_by": extract_rich_text(p, "Requested By"),
                    "reason": extract_rich_text(p, "Reason"),
                    "affects_existing": extract_checkbox(p, "Affects Existing Results"),
                    "needs_frontend": extract_checkbox(p, "Needs Frontend Sync"),
                    "needs_backend": extract_checkbox(p, "Needs Backend Sync"),
                    "needs_scientist": extract_checkbox(p, "Needs Scientist Review"),
                    "created": extract_created_time(p),
                }
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(crs), "change_requests": crs}, indent=2)

        if not crs:
            return "No change requests found."

        # Group by status for kanban view
        status_order = [
            "proposed", "under_review", "approved",
            "implementing", "verified", "closed", "rejected", "archived",
        ]
        grouped: Dict[str, List[Dict]] = {s: [] for s in status_order}
        for cr in crs:
            s = cr["status"]
            if s in grouped:
                grouped[s].append(cr)
            else:
                grouped.setdefault("other", []).append(cr)

        lines = [f"# 🔄 Change Requests ({len(crs)})\n"]
        priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
        for status, items in grouped.items():
            if not items:
                continue
            lines.append(f"## {status.replace('_', ' ').title()} ({len(items)})\n")
            for cr in items:
                pe = priority_emoji.get(cr["priority"], "⚪")
                flags = []
                if cr["affects_existing"]:
                    flags.append("⚠️ affects-existing")
                if cr["needs_frontend"]:
                    flags.append("🖥 frontend")
                if cr["needs_backend"]:
                    flags.append("⚙️ backend")
                if cr["needs_scientist"]:
                    flags.append("🔬 scientist")
                flag_str = f" | {', '.join(flags)}" if flags else ""
                lines.append(f"- {pe} **{cr['title']}** — by {cr['requested_by']}{flag_str}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 11: Update Change Request
# ===================================================================


@mcp.tool(
    name="spechub_update_change_request",
    annotations={
        "title": "Update Change Request",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_update_change_request(
    params: UpdateChangeRequestInput, ctx: Context
) -> str:
    """Update a change request's status, priority, or impact summary.

    Use this to move a CR through the workflow (proposed → under_review →
    approved → implementing → verified → closed).

    Args:
        params: cr_page_id and fields to update.

    Returns:        str: Confirmation of the update.
    """
    try:
        notion = _notion(ctx)
        properties: Dict[str, Any] = {}
        if params.status:
            properties["Status"] = select_property(params.status.value)
        if params.priority:
            properties["Priority"] = select_property(params.priority.value)
        if params.impact_summary is not None:
            properties["Impact Summary"] = rich_text_property(params.impact_summary)

        if not properties:
            return "Error: No fields to update. Provide status, priority, or impact_summary."

        await notion.update_page(params.cr_page_id, properties)

        return json.dumps(
            {
                "status": "success",
                "cr_id": params.cr_page_id,
                "updated_fields": list(properties.keys()),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 12: Log Decision
# ===================================================================


@mcp.tool(
    name="spechub_log_decision",
    annotations={
        "title": "Log Decision",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_log_decision(params: LogDecisionInput, ctx: Context) -> str:
    """Log a decision linked to a change request.

    Creates an immutable decision record with the decision statement,
    alternatives considered, reasoning, and participants. This forms
    the audit trail of *why* decisions were made.

    Args:
        params: Decision details, alternatives, reasoning, participants.

    Returns:
        str: JSON with the created decision log ID.
    """
    try:
        notion = _notion(ctx)

        properties: Dict[str, Any] = {
            "Decision": title_property(params.decision),
            "Reason": rich_text_property(params.reason),
            "Decided By": rich_text_property(params.decided_by),
            "Participants": rich_text_property(", ".join(params.participants) if params.participants else ""),
            "Alternatives Considered": rich_text_property(
                " | ".join(params.alternatives_considered) if params.alternatives_considered else ""
            ),
            "Change Request": relation_property([params.cr_page_id]),
        }

        # Add alternatives as page content for richer formatting
        children = []
        if params.alternatives_considered:
            children.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": rich_text("Alternatives Considered")},
                }
            )
            for alt in params.alternatives_considered:
                children.append(
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": rich_text(alt)},
                    }
                )

        page = await notion.create_page(
            parent={"database_id": _get_db_id("decision_logs")},
            properties=properties,
            children=children if children else None,
            icon={"type": "emoji", "emoji": "⚖️"},
        )

        return json.dumps(
            {
                "status": "success",
                "decision_id": page["id"],
                "decision": params.decision,
                "cr_id": params.cr_page_id,
                "url": page.get("url", ""),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 13: File Bug
# ===================================================================


@mcp.tool(
    name="spechub_file_bug",
    annotations={
        "title": "File Bug Report",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_file_bug(params: FileBugInput, ctx: Context) -> str:
    """File a bug report with optional @mention of the assignee.

    Creates a bug in the Bugs database linked to relevant specs and
    projects. If an assignee_user_id is provided, a comment is added
    to the bug page that @mentions the assignee in Notion.

    Args:
        params: Bug details, severity, assignee, linked specs.

    Returns:
        str: JSON with bug ID and mention status.
    """
    try:
        notion = _notion(ctx)

        properties: Dict[str, Any] = {
            "Title": title_property(params.title),
            "Severity": select_property(params.severity.value),
            "Status": select_property("open"),
            "Reporter": rich_text_property(params.reporter),
            "Description": rich_text_property(params.description),            "Expected Behavior": rich_text_property(params.expected_behavior),
            "Actual Behavior": rich_text_property(params.actual_behavior),
        }

        if params.assignee_user_id:
            properties["Assignee"] = {"people": [{"id": params.assignee_user_id}]}

        if params.project_name:
            project_id = await _find_project_id(notion, params.project_name)
            properties["Project"] = relation_property([project_id])

        spec_ids = await _find_spec_ids_by_names(notion, params.linked_spec_names)
        if spec_ids:
            properties["Linked Specs"] = relation_property(spec_ids)

        # Build page content
        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": rich_text("Bug Report")},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text(params.description)},
            },
        ]
        if params.expected_behavior:
            children.extend(
                [
                    {
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": rich_text("Expected Behavior")},
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": rich_text(params.expected_behavior)},
                    },
                ]
            )
        if params.actual_behavior:
            children.extend(
                [
                    {
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": rich_text("Actual Behavior")},
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": rich_text(params.actual_behavior)},
                    },
                ]
            )

        bug_page = await notion.create_page(
            parent={"database_id": _get_db_id("bugs")},
            properties=properties,
            children=children,
            icon={"type": "emoji", "emoji": "🐛"},
        )

        # @mention assignee via comment
        mention_sent = False
        if params.assignee_user_id:
            try:
                comment_text: List[Dict[str, Any]] = [
                    {"type": "text", "text": {"content": "🐛 Bug assigned to you: "}},
                    mention_user(params.assignee_user_id),
                    {
                        "type": "text",
                        "text": {
                            "content": f"\n\nSeverity: {params.severity.value.upper()}\n{params.title}"
                        },
                    },
                ]
                await notion.create_comment(bug_page["id"], comment_text)
                mention_sent = True
            except Exception:
                # Comment creation may fail if integration lacks comment permission
                mention_sent = False

        return json.dumps(
            {
                "status": "success",
                "bug_id": bug_page["id"],
                "title": params.title,
                "severity": params.severity.value,
                "assignee_mentioned": mention_sent,
                "linked_specs": len(spec_ids),
                "url": bug_page.get("url", ""),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 14: List Bugs
# ===================================================================


@mcp.tool(
    name="spechub_list_bugs",
    annotations={
        "title": "List Bugs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_list_bugs(params: ListBugsInput, ctx: Context) -> str:
    """List bug reports with optional filters.

    Args:
        params: Filters (severity, status) and output format.

    Returns:
        str: List of bugs.
    """
    try:
        notion = _notion(ctx)
        db_id = _get_db_id("bugs")

        filters: List[Dict[str, Any]] = []
        if params.severity:
            filters.append({"property": "Severity", "select": {"equals": params.severity.value}})
        if params.status:
            filters.append({"property": "Status", "select": {"equals": params.status.value}})

        filter_obj = None
        if len(filters) == 1:
            filter_obj = filters[0]
        elif len(filters) > 1:
            filter_obj = {"and": filters}

        result = await notion.query_database(
            db_id,
            filter_obj=filter_obj,            sorts=[{"property": "Severity", "direction": "ascending"}],
        )
        pages = result.get("results", [])

        bugs = []
        for p in pages:
            bugs.append(
                {
                    "id": extract_page_id(p),
                    "title": extract_title(p, "Title"),
                    "severity": extract_select(p, "Severity"),
                    "status": extract_select(p, "Status"),
                    "reporter": extract_rich_text(p, "Reporter"),
                    "description": extract_rich_text(p, "Description"),
                    "created": extract_created_time(p),
                }
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(bugs), "bugs": bugs}, indent=2)

        if not bugs:
            return "No bugs found."
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
        lines = [f"# 🐛 Bug Reports ({len(bugs)})\n"]
        for b in bugs:
            se = severity_emoji.get(b["severity"], "⚪")
            lines.append(f"- {se} **{b['title']}** [{b['status']}] — reported by {b['reporter']}")
            if b["description"]:
                lines.append(f"  {b['description'][:120]}{'...' if len(b['description']) > 120 else ''}")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 15: Update Bug
# ===================================================================


@mcp.tool(
    name="spechub_update_bug",
    annotations={
        "title": "Update Bug",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_update_bug(params: UpdateBugInput, ctx: Context) -> str:
    """Update a bug report's status, severity, or assignee.

    If a new assignee_user_id is provided, a comment @mentioning
    them is added to the bug page.

    Args:
        params: bug_page_id and fields to update.

    Returns:
        str: Confirmation.
    """
    try:
        notion = _notion(ctx)
        properties: Dict[str, Any] = {}
        if params.status:
            properties["Status"] = select_property(params.status.value)
        if params.severity:
            properties["Severity"] = select_property(params.severity.value)
        if params.assignee_user_id:
            properties["Assignee"] = {"people": [{"id": params.assignee_user_id}]}

        if not properties:
            return "Error: No fields to update."

        await notion.update_page(params.bug_page_id, properties)

        # @mention new assignee
        if params.assignee_user_id:
            try:
                await notion.create_comment(
                    params.bug_page_id,
                    [
                        {"type": "text", "text": {"content": "🔄 Bug reassigned to "}},
                        mention_user(params.assignee_user_id),
                    ],
                )
            except Exception:
                pass

        return json.dumps(
            {
                "status": "success",
                "bug_id": params.bug_page_id,
                "updated_fields": list(properties.keys()),
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 16: Get Overview
# ===================================================================


@mcp.tool(
    name="spechub_get_overview",
    annotations={
        "title": "Get Dashboard Overview",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_get_overview(params: GetOverviewInput, ctx: Context) -> str:
    """Get a dashboard overview of the entire Spec Hub workspace.

    Returns counts of projects, specs, CRs, bugs, and highlights
    risk flags (e.g., critical bugs, CRs affecting existing results).

    Args:
        params: Output format.

    Returns:
        str: Dashboard overview.
    """
    try:
        notion = _notion(ctx)

        # Gather counts
        projects = await notion.query_database(_get_db_id("projects"))
        specs = await notion.query_database(_get_db_id("spec_items"))
        crs = await notion.query_database(_get_db_id("change_requests"))
        bugs = await notion.query_database(_get_db_id("bugs"))
        decisions = await notion.query_database(_get_db_id("decision_logs"))

        project_count = len(projects.get("results", []))
        spec_count = len(specs.get("results", []))
        cr_count = len(crs.get("results", []))
        bug_count = len(bugs.get("results", []))
        decision_count = len(decisions.get("results", []))

        # Compute risk flags
        active_crs = [
            cr for cr in crs.get("results", [])            if extract_select(cr, "Status") in ("proposed", "under_review", "implementing")
        ]
        critical_bugs = [
            b for b in bugs.get("results", [])
            if extract_select(b, "Severity") == "critical"
            and extract_select(b, "Status") in ("open", "investigating")
        ]
        affecting_existing = [
            cr for cr in active_crs if extract_checkbox(cr, "Affects Existing Results")
        ]
        pending_reviews = [
            s for s in specs.get("results", [])
            if extract_select(s, "Status") == "review"
        ]

        overview = {
            "metrics": {
                "projects": project_count,
                "spec_items": spec_count,
                "change_requests": cr_count,
                "bugs": bug_count,
                "decision_logs": decision_count,
            },
            "active_crs": len(active_crs),
            "critical_bugs": len(critical_bugs),
            "crs_affecting_existing": len(affecting_existing),
            "specs_pending_review": len(pending_reviews),
        }

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(overview, indent=2)

        lines = ["# 📋 Spec Hub Dashboard\n"]
        lines.append("## Metrics\n")
        lines.append(f"| Metric | Count |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Projects | {project_count} |")
        lines.append(f"| Spec Items | {spec_count} |")
        lines.append(f"| Change Requests | {cr_count} |")
        lines.append(f"| Bugs | {bug_count} |")
        lines.append(f"| Decision Logs | {decision_count} |")
        lines.append("")

        # Risk flags
        risks = []
        if critical_bugs:
            risks.append(f"🔴 **{len(critical_bugs)} critical bug(s)** open")
        if affecting_existing:
            risks.append(f"⚠️ **{len(affecting_existing)} CR(s)** affect existing results")
        if pending_reviews:
            risks.append(f"🟡 **{len(pending_reviews)} spec(s)** pending review")
        if len(active_crs) > 5:
            risks.append(f"📋 **{len(active_crs)} active CRs** — consider prioritising")

        if risks:
            lines.append("## ⚠️ Risk Flags\n")
            for r in risks:
                lines.append(f"- {r}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 17: Get Timeline
# ===================================================================


@mcp.tool(
    name="spechub_get_timeline",
    annotations={
        "title": "Get Audit Timeline",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_get_timeline(params: GetTimelineInput, ctx: Context) -> str:
    """Get a unified audit timeline of all Spec Hub activity.

    Merges spec versions, change requests, decision logs, and bugs
    into a single chronological feed sorted by creation time.

    Args:
        params: limit and output format.

    Returns:
        str: Chronological timeline of all events.
    """
    try:
        notion = _notion(ctx)
        events: List[Dict[str, Any]] = []

        # Fetch from all databases
        for db_key, event_type, title_prop in [
            ("spec_versions", "spec_version", "Name"),
            ("change_requests", "change_request", "Title"),
            ("decision_logs", "decision", "Decision"),
            ("bugs", "bug", "Title"),
        ]:
            try:
                result = await notion.query_database(
                    _get_db_id(db_key),
                    sorts=[{"timestamp": "created_time", "direction": "descending"}],
                    page_size=min(params.limit, 50),
                )
                for p in result.get("results", []):
                    events.append(
                        {
                            "type": event_type,
                            "id": extract_page_id(p),
                            "title": extract_title(p, title_prop),
                            "created": extract_created_time(p),
                            "details": _timeline_details(p, event_type),
                        }
                    )
            except Exception:
                continue

        # Sort by time descending
        events.sort(key=lambda e: e["created"], reverse=True)
        events = events[: params.limit]

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(events), "events": events}, indent=2)

        if not events:
            return "No activity found in the timeline."

        type_emoji = {
            "spec_version": "📝",
            "change_request": "🔄",
            "decision": "⚖️",
            "bug": "🐛",
        }
        lines = [f"# 🕐 Spec Hub Timeline (latest {len(events)} events)\n"]        for e in events:
            emoji = type_emoji.get(e["type"], "📎")
            ts = e["created"][:16].replace("T", " ") if e["created"] else "?"
            lines.append(f"**{ts}** {emoji} `{e['type']}` — **{e['title']}**")
            if e["details"]:
                lines.append(f"  {e['details']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


def _timeline_details(page: Dict[str, Any], event_type: str) -> str:
    """Extract brief detail text for timeline events."""
    if event_type == "spec_version":
        summary = extract_rich_text(page, "Summary")
        by = extract_rich_text(page, "Proposed By")
        return f"by {by}: {summary}" if by else summary
    elif event_type == "change_request":
        by = extract_rich_text(page, "Requested By")
        reason = extract_rich_text(page, "Reason")
        return f"by {by}: {reason}" if by else reason
    elif event_type == "decision":
        by = extract_rich_text(page, "Decided By")
        reason = extract_rich_text(page, "Reason")
        return f"by {by}: {reason}" if by else reason
    elif event_type == "bug":
        reporter = extract_rich_text(page, "Reporter")
        severity = extract_select(page, "Severity")
        return f"[{severity}] reported by {reporter}" if reporter else f"[{severity}]"
    return ""


# ===================================================================
# TOOL 18: Search
# ===================================================================


@mcp.tool(
    name="spechub_search",
    annotations={
        "title": "Search Spec Hub",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_search(params: SearchInput, ctx: Context) -> str:
    """Search across the entire Spec Hub workspace.

    Uses Notion's search API to find pages matching the query across
    all databases (specs, CRs, decisions, bugs).

    Args:
        params: Search query and output format.

    Returns:
        str: Search results with page titles, types, and IDs.
    """
    try:
        notion = _notion(ctx)
        result = await notion.search(query=params.query, page_size=20)

        hits = []
        for p in result.get("results", []):
            if p.get("object") != "page":
                continue
            # Try to determine the type from parent database
            parent = p.get("parent", {})
            db_id = parent.get("database_id", "")

            hit_type = "page"
            for key, stored_id in _db_ids.items():
                if stored_id.replace("-", "") == db_id.replace("-", ""):
                    hit_type = key
                    break

            # Extract title from first available title property
            title = ""
            for prop_name in ["Name", "Title", "Decision"]:
                title = extract_title(p, prop_name)
                if title:
                    break

            hits.append(
                {
                    "id": extract_page_id(p),
                    "title": title,
                    "type": hit_type,
                    "url": p.get("url", ""),
                    "created": extract_created_time(p),
                    "last_edited": p.get("last_edited_time", ""),
                }
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(hits), "results": hits}, indent=2)

        if not hits:
            return f"No results found for '{params.query}'."

        type_emoji = {
            "projects": "📋", "spec_items": "📐", "spec_versions": "📝",
            "change_requests": "🔄", "decision_logs": "⚖️", "bugs": "🐛", "page": "📄",
        }
        lines = [f"# 🔍 Search: '{params.query}' ({len(hits)} results)\n"]
        for h in hits:
            emoji = type_emoji.get(h["type"], "📄")
            lines.append(f"- {emoji} **{h['title']}** (`{h['type']}`) — [open]({h['url']})")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 19: List Users
# ===================================================================


@mcp.tool(
    name="spechub_list_users",
    annotations={
        "title": "List Workspace Users",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def spechub_list_users(params: ListUsersInput, ctx: Context) -> str:
    """List all users in the Notion workspace.

    Useful for finding user IDs to use with @mention features
    (e.g., when filing bugs or assigning CRs).

    Args:
        params: Output format.

    Returns:
        str: List of workspace users with IDs and names.
    """
    try:
        notion = _notion(ctx)
        result = await notion.list_users()
        users = []        for u in result.get("results", []):
            if u.get("type") == "person":
                users.append(
                    {
                        "id": u["id"],
                        "name": u.get("name", "Unknown"),
                        "email": u.get("person", {}).get("email", ""),
                        "avatar_url": u.get("avatar_url", ""),
                    }
                )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(users), "users": users}, indent=2)

        if not users:
            return "No users found in the workspace."
        lines = [f"# 👥 Workspace Users ({len(users)})\n"]
        for u in users:
            email_str = f" ({u['email']})" if u["email"] else ""
            lines.append(f"- **{u['name']}**{email_str} — ID: `{u['id']}`")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ===================================================================
# TOOL 20: Create Impact Link
# ===================================================================


@mcp.tool(
    name="spechub_create_impact_link",
    annotations={
        "title": "Create Impact Link",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def spechub_create_impact_link(
    params: CreateImpactLinkInput, ctx: Context
) -> str:
    """Create a directional impact link between two spec items.

    Records that a change in one spec (source) impacts another (target),
    with the type of impact (definition, ui, api, analysis). The link
    is stored as a comment on both spec pages for traceability.

    Args:
        params: from_spec, to_spec, impact_type, note.

    Returns:
        str: Confirmation of the link creation.
    """
    try:
        notion = _notion(ctx)

        # Get names for readability
        from_page = await notion.get_page(params.from_spec_page_id)
        to_page = await notion.get_page(params.to_spec_page_id)
        from_name = extract_title(from_page)
        to_name = extract_title(to_page)

        impact_label = params.impact_type.value.upper()
        note_str = f" — {params.note}" if params.note else ""

        # Add comment on source spec
        await notion.create_comment(
            params.from_spec_page_id,
            rich_text(
                f"🔗 IMPACT [{impact_label}] → {to_name}{note_str}"
            ),
        )

        # Add comment on target spec
        await notion.create_comment(
            params.to_spec_page_id,
            rich_text(
                f"🔗 IMPACTED BY [{impact_label}] ← {from_name}{note_str}"
            ),
        )

        return json.dumps(
            {
                "status": "success",
                "from": {"id": params.from_spec_page_id, "name": from_name},
                "to": {"id": params.to_spec_page_id, "name": to_name},
                "impact_type": params.impact_type.value,
                "note": params.note,
            },
            indent=2,
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
