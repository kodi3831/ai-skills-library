"""
Static argparse introspection via ast.parse() — no imports, no subprocess.
Produces ToolSpec objects for all skills scripts at server startup.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArgSpec:
    flag: str             # CLI flag, e.g. "--deployment-id"
    dest: str             # Python name, e.g. "deployment_id"
    help: str
    type_name: str        # "str", "int", or "bool"
    required: bool
    choices: list[str] | None
    default: object


@dataclass
class ToolSpec:
    name: str             # MCP tool name, e.g. "aicore_lifecycle_management__get_deployments"
    description: str
    script_path: Path
    args: list[ArgSpec] = field(default_factory=list)
    is_destructive: bool = False  # True when script requires --confirm

    @property
    def input_schema(self) -> dict:
        props: dict = {}
        required_names: list[str] = []
        for a in self.args:
            if a.dest == "confirm":
                continue  # hidden; runner auto-injects --confirm
            s: dict = {}
            if a.help:
                s["description"] = a.help
            if a.type_name == "bool":
                s["type"] = "boolean"
            elif a.type_name == "int":
                s["type"] = "integer"
            else:
                s["type"] = "string"
            if a.choices:
                s["enum"] = a.choices
            if a.default is not None:
                s["default"] = a.default
            props[a.dest] = s
            if a.required:
                required_names.append(a.dest)
        result: dict = {"type": "object", "properties": props}
        if required_names:
            result["required"] = required_names
        return result


def discover_tools(skills_root: Path) -> list[ToolSpec]:
    tools: list[ToolSpec] = []
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists():
            continue
        prefix = skill_dir.name.replace("-", "_")
        for script_path in sorted(scripts_dir.glob("*.py")):
            if script_path.name.startswith("_"):
                continue
            try:
                spec = _parse_script(script_path, prefix)
                if spec is not None:
                    tools.append(spec)
            except Exception:
                pass
    return tools


def _parse_script(script_path: Path, skill_prefix: str) -> ToolSpec | None:
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    description = _extract_argparser_description(tree) or _extract_docstring_first_line(tree)
    if not description:
        return None
    args = _extract_args(tree)
    is_destructive = any(a.dest == "confirm" for a in args)
    return ToolSpec(
        name=f"{skill_prefix}__{script_path.stem}",
        description=description,
        script_path=script_path,
        args=args,
        is_destructive=is_destructive,
    )


def _extract_argparser_description(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "ArgumentParser"
        ):
            for kw in node.keywords:
                if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value).strip()
    return ""


def _extract_docstring_first_line(tree: ast.AST) -> str:
    if (
        isinstance(tree, ast.Module)
        and tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        for line in tree.body[0].value.value.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def _extract_args(tree: ast.AST) -> list[ArgSpec]:
    args: list[ArgSpec] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
        ):
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and str(first.value).startswith("--")):
            continue
        flag = str(first.value)

        kw_map: dict = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if isinstance(kw.value, ast.Constant):
                kw_map[kw.arg] = kw.value.value
            elif isinstance(kw.value, ast.Name):
                kw_map[kw.arg] = kw.value.id
            elif isinstance(kw.value, ast.List):
                kw_map[kw.arg] = [
                    e.value for e in kw.value.elts if isinstance(e, ast.Constant)
                ]

        dest = str(kw_map.get("dest") or flag.lstrip("-").replace("-", "_"))
        action = str(kw_map.get("action", ""))
        if action == "store_true":
            type_name = "bool"
        elif kw_map.get("type") == "int":
            type_name = "int"
        else:
            type_name = "str"

        args.append(
            ArgSpec(
                flag=flag,
                dest=dest,
                help=str(kw_map.get("help", "")),
                type_name=type_name,
                required=kw_map.get("required") is True,
                choices=kw_map.get("choices"),
                default=kw_map.get("default"),
            )
        )
    return args
