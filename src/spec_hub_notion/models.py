"""Pydantic models for Spec Hub MCP tool inputs."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class SpecType(str, Enum):
    """Types of spec items."""
    DASHBOARD = "dashboard"
    PAGE = "page"
    COMPONENT = "component"
    KPI = "kpi"
    PARAMETER = "parameter"
    METRIC_FORMULA = "metric_formula"
    API_CONTRACT = "api_contract"
    EXPERIMENT_LABEL = "experiment_label"
    ALERT_RULE = "alert_rule"


class SpecStatus(str, Enum):
    """Status of a spec item."""
    DRAFT = "draft"
    ACTIVE = "active"
    REVIEW = "review"
    DEPRECATED = "deprecated"


class VersionStatus(str, Enum):
    """Status of a spec version."""
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DEPRECATED = "deprecated"


class ChangeType(str, Enum):
    """Type of change in a version."""
    ADD = "add"
    MODIFY = "modify"
    DEPRECATE = "deprecate"


class CRStatus(str, Enum):
    """Change request status (workflow)."""
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    IMPLEMENTING = "implementing"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Priority(str, Enum):
    """Priority level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BugSeverity(str, Enum):
    """Bug severity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BugStatus(str, Enum):
    """Bug status."""
    OPEN = "open"
    INVESTIGATING = "investigating"
    FIX_IN_PROGRESS = "fix_in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    WONT_FIX = "wont_fix"


class ImpactType(str, Enum):
    """Type of impact between spec items."""
    DEFINITION = "definition"
    UI = "ui"
    API = "api"
    ANALYSIS = "analysis"


class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------


class SetupWorkspaceInput(BaseModel):
    """Input for setting up the Spec Hub workspace in Notion."""
    model_config = ConfigDict(str_strip_whitespace=True)

    parent_page_id: str = Field(
        ...,
        description="Notion page ID where Spec Hub databases will be created. "
        "Find it from the page URL: notion.so/Your-Page-{PAGE_ID}",
        min_length=1,
    )


class CreateProjectInput(BaseModel):
    """Input for creating a new project."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="Project name (e.g., 'Neuro Dashboard Reliability')", min_length=1, max_length=200)
    description: str = Field(default="", description="Project description", max_length=2000)
    owner: str = Field(..., description="Project owner name or Notion user ID", min_length=1)
    status: str = Field(default="active", description="Project status: active, paused, or archived")


class ListProjectsInput(BaseModel):
    """Input for listing projects."""
    model_config = ConfigDict(str_strip_whitespace=True)

    status: Optional[str] = Field(default=None, description="Filter by status (active/paused/archived)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class CreateSpecInput(BaseModel):
    """Input for creating a spec item."""
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: str = Field(..., description="Name of the parent project", min_length=1)
    name: str = Field(..., description="Spec item name (e.g., 'deposition_stability_score')", min_length=1, max_length=200)
    type: SpecType = Field(..., description="Spec type (dashboard, kpi, component, api_contract, etc.)")
    owner: str = Field(..., description="Spec owner name", min_length=1)
    status: SpecStatus = Field(default=SpecStatus.DRAFT, description="Initial status")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization", max_length=10)
    summary: str = Field(default="", description="Brief summary of this spec", max_length=2000)
    content_json: str = Field(default="{}", description="Structured spec content as JSON string")


class ListSpecsInput(BaseModel):
    """Input for listing/searching spec items."""
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: Optional[str] = Field(default=None, description="Filter by project name")
    type: Optional[SpecType] = Field(default=None, description="Filter by spec type")
    status: Optional[SpecStatus] = Field(default=None, description="Filter by status")
    owner: Optional[str] = Field(default=None, description="Filter by owner name")
    query: Optional[str] = Field(default=None, description="Search query text")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class GetSpecInput(BaseModel):
    """Input for getting spec detail with versions."""
    model_config = ConfigDict(str_strip_whitespace=True)

    spec_page_id: str = Field(..., description="Notion page ID of the spec item", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class CreateSpecVersionInput(BaseModel):
    """Input for creating a new spec version."""
    model_config = ConfigDict(str_strip_whitespace=True)

    spec_page_id: str = Field(..., description="Notion page ID of the parent spec item", min_length=1)
    version_number: int = Field(..., description="Version number (e.g., 2)", ge=1)
    content_json: str = Field(..., description="Structured content as JSON string", min_length=2)
    summary: str = Field(..., description="What changed in this version", min_length=1, max_length=2000)
    rationale: str = Field(default="", description="Why this change was made", max_length=2000)
    change_type: ChangeType = Field(default=ChangeType.MODIFY, description="Type of change: add, modify, or deprecate")
    proposed_by: str = Field(..., description="Name of the person proposing this version", min_length=1)


class ApproveVersionInput(BaseModel):
    """Input for approving a spec version."""
    model_config = ConfigDict(str_strip_whitespace=True)

    version_page_id: str = Field(..., description="Notion page ID of the version to approve", min_length=1)
    approved_by: str = Field(..., description="Name of the approver", min_length=1)


class CreateChangeRequestInput(BaseModel):
    """Input for creating a change request."""
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: str = Field(..., description="Parent project name", min_length=1)
    title: str = Field(..., description="Change request title", min_length=1, max_length=300)
    description: str = Field(default="", description="Detailed description of the change", max_length=5000)
    proposed_change: str = Field(..., description="What specifically is being changed", min_length=1, max_length=3000)
    reason: str = Field(..., description="Why this change is needed", min_length=1, max_length=2000)
    requested_by: str = Field(..., description="Requester name", min_length=1)
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority: low, medium, high, critical")
    linked_spec_names: List[str] = Field(default_factory=list, description="Names of linked spec items")
    impact_summary: str = Field(default="", description="Summary of impact across systems", max_length=2000)
    affects_existing_results: bool = Field(default=False, description="Whether this change affects existing interpretations")
    needs_frontend_sync: bool = Field(default=False, description="Requires frontend changes")
    needs_backend_sync: bool = Field(default=False, description="Requires backend changes")
    needs_scientist_review: bool = Field(default=False, description="Requires scientist/domain expert review")


class ListChangeRequestsInput(BaseModel):
    """Input for listing change requests."""
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: Optional[str] = Field(default=None, description="Filter by project name")
    status: Optional[CRStatus] = Field(default=None, description="Filter by status")
    priority: Optional[Priority] = Field(default=None, description="Filter by priority")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class UpdateChangeRequestInput(BaseModel):
    """Input for updating a change request."""
    model_config = ConfigDict(str_strip_whitespace=True)

    cr_page_id: str = Field(..., description="Notion page ID of the change request", min_length=1)
    status: Optional[CRStatus] = Field(default=None, description="New status")
    priority: Optional[Priority] = Field(default=None, description="New priority")
    impact_summary: Optional[str] = Field(default=None, description="Updated impact summary", max_length=2000)


class LogDecisionInput(BaseModel):
    """Input for logging a decision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    cr_page_id: str = Field(..., description="Notion page ID of the related change request", min_length=1)
    decision: str = Field(..., description="The decision statement", min_length=1, max_length=3000)
    alternatives_considered: List[str] = Field(default_factory=list, description="Alternative options that were considered")
    reason: str = Field(..., description="Reasoning behind the decision", min_length=1, max_length=3000)
    decided_by: str = Field(..., description="Person who made the decision", min_length=1)
    participants: List[str] = Field(default_factory=list, description="People involved in the decision")


class FileBugInput(BaseModel):
    """Input for filing a bug report."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., description="Bug title", min_length=1, max_length=300)
    description: str = Field(..., description="Detailed bug description with reproduction steps", min_length=1, max_length=5000)
    severity: BugSeverity = Field(default=BugSeverity.MEDIUM, description="Severity: low, medium, high, critical")
    reporter: str = Field(..., description="Person reporting the bug", min_length=1)
    assignee_user_id: Optional[str] = Field(default=None, description="Notion user ID of the assignee (for @mention)")
    linked_spec_names: List[str] = Field(default_factory=list, description="Names of related spec items")
    project_name: Optional[str] = Field(default=None, description="Related project name")
    expected_behavior: str = Field(default="", description="What was expected to happen", max_length=2000)
    actual_behavior: str = Field(default="", description="What actually happened", max_length=2000)


class ListBugsInput(BaseModel):
    """Input for listing bugs."""
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: Optional[str] = Field(default=None, description="Filter by project name")
    severity: Optional[BugSeverity] = Field(default=None, description="Filter by severity")
    status: Optional[BugStatus] = Field(default=None, description="Filter by status")
    assignee: Optional[str] = Field(default=None, description="Filter by assignee name")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class UpdateBugInput(BaseModel):
    """Input for updating a bug."""
    model_config = ConfigDict(str_strip_whitespace=True)

    bug_page_id: str = Field(..., description="Notion page ID of the bug", min_length=1)
    status: Optional[BugStatus] = Field(default=None, description="New status")
    severity: Optional[BugSeverity] = Field(default=None, description="New severity")
    assignee_user_id: Optional[str] = Field(default=None, description="New assignee Notion user ID")


class GetOverviewInput(BaseModel):
    """Input for getting the dashboard overview."""
    model_config = ConfigDict(str_strip_whitespace=True)

    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class GetTimelineInput(BaseModel):
    """Input for getting the audit timeline."""
    model_config = ConfigDict(str_strip_whitespace=True)

    limit: int = Field(default=20, description="Max events to return", ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class SearchInput(BaseModel):
    """Input for searching across the workspace."""
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., description="Search query", min_length=1, max_length=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")


class CreateImpactLinkInput(BaseModel):
    """Input for creating an impact link between spec items."""
    model_config = ConfigDict(str_strip_whitespace=True)

    from_spec_page_id: str = Field(..., description="Source spec item Notion page ID", min_length=1)
    to_spec_page_id: str = Field(..., description="Target spec item Notion page ID", min_length=1)
    impact_type: ImpactType = Field(..., description="Type of impact: definition, ui, api, analysis")
    note: str = Field(default="", description="Description of the relationship", max_length=1000)


class ListUsersInput(BaseModel):
    """Input for listing workspace users."""
    model_config = ConfigDict(str_strip_whitespace=True)

    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")
