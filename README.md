# Spec Hub for Notion

> **Engineering Spec Management System powered by Notion MCP** — track specs, change requests, decisions, and bugs in Notion with full traceability, @mention support, and cross-linking.

Built for the [Notion MCP Challenge](https://dev.to/devteam/join-the-notion-mcp-challenge-1500-in-prizes-73e).

---

## What It Does

Spec Hub turns your Notion workspace into a structured engineering specification management system. It bridges the gap between internal engineering teams and external collaborators by providing:

- **Structured Spec Registry** — Versioned specs (KPIs, API contracts, components, parameters, etc.) with JSON content, diff-ready history, and approval workflows
- **Change Request Board** — Kanban-style workflow tracking from `proposed → under_review → approved → implementing → verified → closed`, with impact flags showing which teams need to sync
- **Decision Logs** — Immutable records of *why* decisions were made, with alternatives considered and participants recorded
- **Bug Tracking with @Mentions** — File bugs linked to specs, auto-mention assignees in Notion comments so they get notified immediately
- **Impact Links** — Track how specs depend on each other (definition, UI, API, analysis) so you can see ripple effects of changes
- **Audit Timeline** — Unified chronological view of all activity across specs, CRs, decisions, and bugs
- **Dashboard Overview** — At-a-glance metrics with risk flags (critical bugs, CRs affecting existing results, pending reviews)

### Why Notion?

Engineering teams already live in Notion. Instead of building yet another standalone tool that creates context-switching, Spec Hub embeds directly into your existing workspace. Notion's databases give us structured data, relations give us cross-linking, comments give us @mentions, and the MCP protocol makes it all programmable through AI assistants.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   AI Assistant                   │
│          (Claude, Cursor, VS Code, etc.)         │
└──────────────────────┬──────────────────────────┘
                       │ MCP Protocol (stdio)
┌──────────────────────▼──────────────────────────┐
│            spec_hub_notion_mcp                   │
│                                                  │
│  20 tools for spec management workflows          │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │  Projects   │ │   Specs    │ │  Versions    │ │
│  │  CRUD       │ │  CRUD +    │ │  Create +    │ │
│  │             │ │  Search    │ │  Approve     │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │  Change     │ │  Decision  │ │  Bugs        │ │
│  │  Requests   │ │  Logs      │ │  + @mention  │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │  Timeline   │ │  Overview  │ │  Search      │ │
│  │  Audit      │ │  Dashboard │ │  + Users     │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │ Notion REST API v1
┌──────────────────────▼──────────────────────────┐
│              Notion Workspace                    │
│                                                  │
│  📋 Projects DB    📐 Spec Items DB              │
│  📝 Versions DB    🔄 Change Requests DB         │
│  ⚖️ Decisions DB   🐛 Bugs DB                    │
│                                                  │
│  Relations, Views, Comments, @Mentions           │
└─────────────────────────────────────────────────┘
```

---

## Setup

### 1. Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"New integration"**
3. Give it a name (e.g., "Spec Hub")
4. Select your workspace
5. Under **Capabilities**, enable:
   - Read content
   - Update content
   - Insert content
   - Read comments
   - Create comments
   - Read user information including email addresses
6. Copy the **Internal Integration Secret** (starts with `ntn_`)

### 2. Prepare a Parent Page

1. Create a new page in Notion (e.g., "🏗 Spec Hub")
2. Click the **⋯** menu → **Connections** → Add your integration
3. Copy the page ID from the URL: `notion.so/Your-Page-{PAGE_ID}`

### 3. Install Spec Hub

```bash
# Clone the repo
git clone https://github.com/your-username/spec-hub-notion.git
cd spec-hub-notion

# Install dependencies
pip install -e .

# Set environment variables
export NOTION_API_TOKEN="ntn_your_token_here"
export NOTION_PARENT_PAGE_ID="your-page-id-here"
```

### 4. Configure Your AI Assistant

#### Claude Desktop / Claude Code

Add to your MCP config (`claude_desktop_config.json` or `.claude.json`):

```json
{
  "mcpServers": {
    "spec-hub-notion": {
      "command": "python",
      "args": ["-m", "spec_hub_notion.server"],
      "env": {
        "NOTION_API_TOKEN": "ntn_your_token_here"
      }
    }
  }
}
```

#### Cursor / VS Code

Add to `.cursor/mcp.json` or VS Code MCP settings:

```json
{
  "mcpServers": {
    "spec-hub-notion": {
      "command": "python",
      "args": ["-m", "spec_hub_notion.server"],
      "env": {
        "NOTION_API_TOKEN": "ntn_your_token_here"
      }
    }
  }
}
```

---

## Usage

### First-Time Setup

Ask your AI assistant:

> "Set up the Spec Hub workspace in Notion. Use this parent page ID: `abc123...`"

This creates all 6 databases with proper schemas, relations, and select options.

### Core Workflows

#### 1. Define a Spec

> "Create a new KPI spec called 'deposition_stability_score' in the 'Neuro Dashboard' project, owned by Alice. The content is: `{"formula": "smoothed_slope(raw_values, window=5)", "threshold": 0.8, "unit": "score"}`"

#### 2. Submit a Change Request

> "Submit a change request to raise the stability warning threshold. It affects the deposition_stability_score KPI and the RiskHighlightCard component. It affects existing results and needs both backend and scientist review."

#### 3. Log a Decision

> "Log a decision on CR-123: We chose the smoothed slope approach. Alternatives were raw slope only and lowering the threshold. Alice, Bob, and Carol participated."

#### 4. File a Bug with @Mention

> "File a critical bug: the stability score returns NaN when the input array has fewer than 5 data points. Assign it to Bob (get his user ID first) and link it to the deposition_stability_score spec."

#### 5. Check the Dashboard

> "Show me the Spec Hub dashboard overview."

#### 6. View the Audit Timeline

> "Show the latest 20 events in the Spec Hub timeline."

---

## All 20 MCP Tools

| Tool | Description |
|------|-------------|
| `spechub_setup_workspace` | Create all databases in a Notion page |
| `spechub_create_project` | Create a new project |
| `spechub_list_projects` | List projects with optional status filter |
| `spechub_create_spec` | Create a spec item with auto-generated v1 |
| `spechub_list_specs` | List/search specs by type, status, owner |
| `spechub_get_spec` | Get spec detail with version history and linked CRs |
| `spechub_create_spec_version` | Create a new version of a spec |
| `spechub_approve_version` | Approve a version (deprecates previous) |
| `spechub_create_change_request` | Create a CR with impact flags |
| `spechub_list_change_requests` | List CRs in kanban-style grouping |
| `spechub_update_change_request` | Move a CR through the workflow |
| `spechub_log_decision` | Record a decision with alternatives |
| `spechub_file_bug` | File a bug with @mention assignee |
| `spechub_list_bugs` | List bugs by severity/status |
| `spechub_update_bug` | Update bug status/assignee with @mention |
| `spechub_get_overview` | Dashboard metrics and risk flags |
| `spechub_get_timeline` | Unified audit trail |
| `spechub_search` | Full-text search across all databases |
| `spechub_list_users` | List workspace users for @mention |
| `spechub_create_impact_link` | Link spec dependencies via comments |

---

## Data Model

### Entity Relationships

```
Project ─┬── Spec Item ──── Spec Version
         │        │
         │        ├── Impact Links (via comments)
         │        │
         ├── Change Request ──── Decision Log
         │        │
         │        └── Linked Specs (relation)
         │
         └── Bug Report
                  │
                  └── Linked Specs (relation)
                  └── @Mention Assignee (comment)
```

### Databases Created by Setup

| Database | Key Properties |
|----------|---------------|
| **Projects** | Name, Description, Owner, Status |
| **Spec Items** | Name, Type, Owner, Status, Tags, Current Version, Project (relation) |
| **Spec Versions** | Version #, Status, Change Type, Summary, Rationale, Proposed/Approved By, Is Current, Spec Item (relation) |
| **Change Requests** | Title, Status, Priority, Reason, Impact Flags (4 checkboxes), Project + Specs (relations) |
| **Decision Logs** | Decision, Reason, Decided By, Participants, Alternatives, CR (relation) |
| **Bugs** | Title, Severity, Status, Reporter, Assignee (people), Expected/Actual Behavior, Project + Specs (relations) |

---

## How Notion MCP Is Used

This project demonstrates deep integration with the Notion platform through its REST API, designed to work alongside the official Notion MCP server:

1. **Database Creation** (`POST /databases`) — Programmatic workspace setup with typed schemas, select options, and cross-database relations
2. **Page CRUD** (`POST /pages`, `PATCH /pages`) — Creating and updating specs, CRs, decisions, and bugs with structured properties
3. **Database Queries** (`POST /databases/{id}/query`) — Filtered queries with compound conditions (AND/OR) for listing and searching
4. **Block Append** (`PATCH /blocks/{id}/children`) — Storing structured JSON content as code blocks in version pages
5. **Comments with @Mentions** (`POST /comments`) — Filing bugs and creating impact links with user mentions that trigger Notion notifications
6. **User Lookup** (`GET /users`) — Discovering workspace members for @mention assignment
7. **Search** (`POST /search`) — Cross-database full-text search

---

## Tech Stack

- **Python 3.10+** with type hints throughout
- **FastMCP** (MCP Python SDK) for MCP server implementation
- **Pydantic v2** for input validation with constraints
- **httpx** for async HTTP to Notion API
- **Notion REST API v1** (2022-06-28) as the data layer

---

## License

MIT

# Spec Hub for Notion

> Engineering Spec Management System powered by Notion MCP
>
> Bootstrap commit - full source code to follow.
