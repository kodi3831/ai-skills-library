# AI Core Skills — MCP Server

MCP server that exposes all skills in this repository as tools: script-based skills from `plugins/` (SAP AI Core, GenAI Hub) and markdown reference skills from `skills/` (SAP Fiori Guidelines, SAP Fiori iOS).

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or pip

## Setup

**Option A — uv (recommended)**

`uv` auto-installs all dependencies declared in `server.py` on first run — no separate install step needed.

```bash
# Install uv if you don't have it
pip install uv
```

**Option B — pip**

```bash
pip install -r mcp/requirements.txt
```

## Start the server

**stdio transport** (default — used by Claude Code and MCP clients)

```bash
# via uv (handles dependencies automatically)
uv run mcp/server.py

# via Python directly (after pip install)
python mcp/server.py
```

**HTTP transport**

```bash
uv run mcp/server.py --transport http --port 8080

python mcp/server.py --transport http --host 0.0.0.0 --port 8080
```

## Configure in Claude Code

Add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "ai-core-skills": {
      "command": "uv",
      "args": ["run", "mcp/server.py"]
    }
  }
}
```

## Verify

Run the smoke test to confirm all tools are registered:

```bash
uv run mcp/test_server.py
```

## Tools overview

The server registers tools from two locations:

| Source | Pattern | Example |
|--------|---------|---------|
| `plugins/*/skills/*/scripts/*.py` | `<skill>__<action>` | `aicore_lifecycle_management__get_deployments` |
| `skills/*/` (markdown-only) | `<skill>__get_skill`, `<skill>__read_reference` | `sap_fiori_guidelines__get_skill` |

Skills from `plugins/aicore-skills`:

| Skill | Tools |
|-------|-------|
| `aicore-admin-resources` | `check_setup`, `get_token`, `list_resource_groups`, `create_resource_group`, `patch_resource_group`, `delete_resource_group` |
| `aicore-lifecycle-management` | `get_deployments`, `create_deployment`, `stop_deployment`, `delete_deployment`, `patch_deployment`, `get_configurations`, `create_configuration`, `get_scenarios`, `get_executables`, `get_deployment_logs`, `dedup_deployments` |
| `genai-hub-foundation-models` | `list_foundation_models` |
| `genai-hub-tabular-orchestration` | `list_tabular_artifacts`, `get_tabular_artifact`, `create_tabular_artifact`, `delete_tabular_artifact`, `get_tabular_artifact_data`, `list_data_destinations`, `get_data_destination`, `create_data_destination`, `patch_data_destination`, `delete_data_destination`, `validate_data_destination`, `validate_data_destination_by_name`, `search_data_destinations`, `list_scenario_configs`, `get_scenario_config`, `create_scenario_config`, `patch_scenario_config`, `delete_scenario_config`, `search_scenario_configs`, `predict` |
