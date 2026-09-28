"""
Subprocess runner — executes a skills script via `uv run`.

Local dev transport: one subprocess per tool call, PEP 723 dependency isolation.
For in-cluster hosting, replace this module with _runner_sdk.py that makes
in-process async SDK calls instead (sharing the same ToolSpec metadata layer).
"""
from __future__ import annotations

import asyncio
from typing import Any

from _introspect import ToolSpec

_TIMEOUT = 120  # seconds; AI Core API can be slow on cold start


async def run(spec: ToolSpec, kwargs: dict[str, Any]) -> str:
    cli_args = _build_cli_args(spec, kwargs)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", str(spec.script_path), *cli_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"Script timed out after {_TIMEOUT}s")

    if proc.returncode != 0:
        error = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"exit {proc.returncode}: {error}")
    return stdout.decode(errors="replace")


def _build_cli_args(spec: ToolSpec, kwargs: dict[str, Any]) -> list[str]:
    arg_by_dest = {a.dest: a for a in spec.args}
    cli: list[str] = []
    for dest, value in kwargs.items():
        if dest not in arg_by_dest or value is None:
            continue
        a = arg_by_dest[dest]
        if a.type_name == "bool":
            if value:
                cli.append(a.flag)
        else:
            cli.extend([a.flag, str(value)])
    if spec.is_destructive:
        cli.append("--confirm")
    return cli
