"""
Markdown runner — reads reference files from markdown-based skills.

Used for skills that ship SKILL.md + references/ instead of scripts/.
No subprocesses: reads directly from disk.
"""
from __future__ import annotations

from pathlib import Path


def read_skill(skill_md: Path) -> str:
    return skill_md.read_text(encoding="utf-8")


def read_reference(refs_dir: Path, reference: str) -> str:
    ref_path = (refs_dir / reference).resolve()
    if not str(ref_path).startswith(str(refs_dir.resolve())):
        raise ValueError("Path traversal not allowed")
    if not ref_path.exists():
        available = sorted(str(p.relative_to(refs_dir)) for p in refs_dir.rglob("*.md"))
        hint = ", ".join(available[:8])
        if len(available) > 8:
            hint += f", … ({len(available) - 8} more)"
        return f"Reference not found: {reference!r}. Available: {hint}"
    return ref_path.read_text(encoding="utf-8")
