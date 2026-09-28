"""
Smoke test for the MCP server: starts it via subprocess, sends initialize + tools/list,
and verifies the expected tools come back (including markdown skill tools).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SERVER = REPO_ROOT / "mcp" / "server.py"
TIMEOUT = 30

# Markdown skills each register two tools: __get_skill and __read_reference
EXPECTED_MARKDOWN_TOOLS = {
    "sap_fiori_guidelines__get_skill",
    "sap_fiori_guidelines__read_reference",
    "sap_fiori_ios__get_skill",
    "sap_fiori_ios__read_reference",
}

# Script-based tools from the aicore-skills plugin
EXPECTED_PLUGIN_TOOLS = {
    "aicore_lifecycle_management__get_deployments",
    "aicore_lifecycle_management__create_deployment",
    "aicore_admin_resources__list_resource_groups",
    "genai_hub_foundation_models__list_foundation_models",
}


def main() -> None:
    messages = [
        json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "0.1"},
            },
        }),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ]

    proc = subprocess.Popen(
        ["uv", "run", str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    assert proc.stdin and proc.stdout and proc.stderr

    for msg in messages:
        proc.stdin.write(msg + "\n")
    proc.stdin.flush()

    deadline = time.monotonic() + TIMEOUT
    found = False
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("id") == 2:
            tools = payload["result"]["tools"]
            tool_names = {t["name"] for t in tools}
            print(f"OK: {len(tools)} tools registered")
            for t in tools[:5]:
                print(f"  {t['name']}")
            if len(tools) > 5:
                print(f"  ... and {len(tools) - 5} more")

            missing = EXPECTED_MARKDOWN_TOOLS - tool_names
            if missing:
                print(f"FAIL: missing expected markdown tools: {missing}", file=sys.stderr)
                found = False
            else:
                print(f"OK: all {len(EXPECTED_MARKDOWN_TOOLS)} expected markdown tools present")

            missing_plugin = EXPECTED_PLUGIN_TOOLS - tool_names
            if missing_plugin:
                print(f"FAIL: missing expected plugin tools: {missing_plugin}", file=sys.stderr)
                found = False
            else:
                print(f"OK: all {len(EXPECTED_PLUGIN_TOOLS)} expected aicore plugin tools present")
                found = found if missing else True
            break

    proc.terminate()
    proc.wait(timeout=5)

    if not found:
        err = proc.stderr.read()
        print(f"FAIL: no tools/list response within {TIMEOUT}s", file=sys.stderr)
        if err:
            print("stderr:", err[:500], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
