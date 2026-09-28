# /// script
# requires-python = ">=3.11"
# dependencies = ["fastmcp[server]>=4.0.0"]
# ///
"""
AI Core Skills MCP server — local stdio transport.

Two skill types are supported:
  - Script skills: <root>/*/scripts/*.py — discovered via AST introspection,
    each script becomes an MCP tool backed by `uv run`.
  - Markdown skills: <root>/* with SKILL.md + references/ (no scripts/) — each
    skill gets two tools: <skill>__get_skill (returns SKILL.md) and
    <skill>__read_reference (reads a references/ file by relative path).

Skills are discovered from two places:
  - skills/            — top-level skills in this repo
  - plugins/*/skills/  — skills bundled inside Claude Code plugins

Destructive script operations (those with --confirm) are auto-confirmed at
the server layer — the act of calling the tool IS the confirmation.

Run via Claude Code plugin (configured in .mcp.json) or directly:
    uv run mcp/server.py

For in-cluster hosting, swap _runner_subprocess for _runner_sdk (see plan doc).
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Add this directory to sys.path before importing local helpers
sys.path.insert(0, str(Path(__file__).parent))

from _introspect import ToolSpec, discover_tools
from _runner_markdown import read_reference, read_skill
from _runner_subprocess import run

from fastmcp import FastMCP

REPO_ROOT = Path(__file__).parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"
PLUGINS_ROOT = REPO_ROOT / "plugins"

mcp = FastMCP(
    "AI Core Skills",
    instructions=(
        "Tools for SAP AI Core, GenAI Hub, and SAP design guidelines. "
        "Script-based tools follow the pattern <skill>__<action>, e.g. "
        "aicore_lifecycle_management__get_deployments. "
        "Markdown-based skills expose <skill>__get_skill (full overview) and "
        "<skill>__read_reference (read a specific reference file by relative path)."
    ),
)

_PY_TYPE = {"str": str, "int": int, "bool": bool}


def _collect_skills_roots() -> list[Path]:
    """Return all skills roots: top-level skills/ plus each plugins/*/skills/."""
    roots: list[Path] = []
    if SKILLS_ROOT.exists():
        roots.append(SKILLS_ROOT)
    if PLUGINS_ROOT.exists():
        for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
            if not plugin_dir.is_dir():
                continue
            plugin_json = plugin_dir / "plugin.json"
            if not plugin_json.exists():
                continue
            try:
                data = json.loads(plugin_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Resolve the skills root as the parent of the first listed skill path,
            # or fall back to the conventional plugin_dir/skills/ directory.
            skills_list = data.get("skills", [])
            if skills_list:
                first = (plugin_dir / skills_list[0]).resolve().parent
                if first.is_dir():
                    roots.append(first)
                    continue
            fallback = plugin_dir / "skills"
            if fallback.is_dir():
                roots.append(fallback)
    return roots


def _parse_skill_description(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else skill_md.parent.name


def _register_script_tools(skills_root: Path) -> int:
    specs = discover_tools(skills_root)
    for spec in specs:
        _register_tool(spec)
    return len(specs)


def _register_tool(spec: ToolSpec) -> None:
    params: list[inspect.Parameter] = []
    for arg in spec.args:
        if arg.dest == "confirm":
            continue  # hidden; auto-injected by runner for destructive ops
        base = _PY_TYPE.get(arg.type_name, str)
        ann = base if arg.required else Optional[base]
        params.append(
            inspect.Parameter(
                arg.dest,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if arg.required else None,
                annotation=ann,
            )
        )

    captured = spec

    async def _tool_fn(**kwargs: object) -> str:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        return await run(captured, filtered)

    _tool_fn.__name__ = spec.name
    _tool_fn.__doc__ = spec.description
    _tool_fn.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    _tool_fn.__annotations__ = {p.name: p.annotation for p in params}
    _tool_fn.__annotations__["return"] = str

    mcp.add_tool(_tool_fn)


def _register_markdown_skills(skills_root: Path) -> int:
    count = 0
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        if (skill_dir / "scripts").exists():
            continue  # handled as script-based skill

        prefix = skill_dir.name.replace("-", "_")
        skill_desc = _parse_skill_description(skill_md)

        captured_md = skill_md

        async def _get_skill(_md: Path = captured_md) -> str:
            return read_skill(_md)

        _get_skill.__name__ = f"{prefix}__get_skill"
        _get_skill.__doc__ = skill_desc
        _get_skill.__signature__ = inspect.Signature([], return_annotation=str)
        _get_skill.__annotations__ = {"return": str}
        mcp.add_tool(_get_skill)

        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            available_refs = sorted(
                str(p.relative_to(refs_dir)) for p in refs_dir.rglob("*.md")
            )
            ref_hint = "; ".join(available_refs[:6])
            if len(available_refs) > 6:
                ref_hint += f"; … ({len(available_refs) - 6} more)"

            captured_refs = refs_dir

            async def _read_reference(reference: str, _rd: Path = captured_refs) -> str:
                return read_reference(_rd, reference)

            _read_reference.__name__ = f"{prefix}__read_reference"
            _read_reference.__doc__ = (
                f"Read a reference file from the {skill_dir.name} skill. "
                f"Pass the relative path, e.g. 'ui-actions.md' or 'foundations/colors.md'. "
                f"Available: {ref_hint}"
            )
            _read_reference.__signature__ = inspect.Signature(
                [inspect.Parameter("reference", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)],
                return_annotation=str,
            )
            _read_reference.__annotations__ = {"reference": str, "return": str}
            mcp.add_tool(_read_reference)

        count += 1
    return count


for _root in _collect_skills_roots():
    _register_script_tools(_root)
    _register_markdown_skills(_root)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--transport", default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args, _ = parser.parse_known_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
