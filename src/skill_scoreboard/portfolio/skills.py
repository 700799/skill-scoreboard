"""Discover and parse SKILL.md files across a skill library."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from skill_scoreboard.metrics.tokens import estimate_tokens
from skill_scoreboard.models.portfolio import SkillMeta

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
#: Relative path-like tokens in the body (references/foo.md, scripts/run.py, ...).
_PATH_TOKEN = re.compile(r"(?<![\w./-])([\w-]+(?:/[\w.-]+)+\.[A-Za-z0-9]{1,5})")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
#: Markdown that is repository furniture rather than a skill, at any location.
_NON_SKILL_STEMS = {"README", "CHANGELOG", "LICENSE", "CONTRIBUTING", "CODE_OF_CONDUCT"}


def parse_skill(path: Path, *, name: str | None = None) -> SkillMeta:
    raw = path.read_text(encoding="utf-8", errors="replace")
    frontmatter: dict[str, Any] = {}
    body = raw
    match = _FRONTMATTER.match(raw)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1))
            if isinstance(loaded, dict):
                frontmatter = loaded
        except yaml.YAMLError:
            frontmatter = {}
        body = raw[match.end() :]

    if name is None:
        name = path.parent.name if path.name == "SKILL.md" else path.stem
    declared = frontmatter.get("name")
    description = frontmatter.get("description")
    return SkillMeta(
        name=str(declared) if isinstance(declared, str) and declared else name,
        path=str(path),
        description=str(description) if isinstance(description, str) else "",
        body=body,
        frontmatter=frontmatter,
        token_estimate=estimate_tokens(raw),
        referenced_paths=sorted(set(_PATH_TOKEN.findall(body))),
    )


def _inside_any(path: Path, directories: list[Path]) -> bool:
    parents = set(path.parents)
    return any(d in parents for d in directories)


def discover_skills(root: str | Path) -> list[SkillMeta]:
    """Find every skill under ``root``.

    Two layouts count as a skill: a bundle directory (``<name>/SKILL.md``) and a
    flat file (``<name>.md``). Plugin trees nest skills arbitrarily deep, so the
    search is recursive.

    Everything *inside* a bundle belongs to that bundle. A bundle's own
    ``references/``, ``examples/`` and stray notes are supporting files it ships,
    not separate skills, and a ``SKILL.md`` nested under another bundle is a
    worked example rather than a skill of its own. Counting those as skills used
    to invent entries that no one wrote, each failing the lint checks a real
    skill passes and dragging the whole library's score down with it.
    """
    root_path = Path(root)
    if root_path.is_file():
        return [parse_skill(root_path)]
    if not root_path.is_dir():
        raise FileNotFoundError(f"skills directory not found: {root_path}")

    found: dict[str, SkillMeta] = {}
    bundles: list[Path] = []

    # Shallowest first, so an outer bundle is claimed before anything nested in it.
    for path in sorted(root_path.rglob("SKILL.md"), key=lambda p: (len(p.parts), p)):
        if _SKIP_DIRS & set(path.parts) or _inside_any(path, bundles):
            continue
        bundles.append(path.parent)
        meta = parse_skill(path)
        found[meta.name] = meta

    for path in sorted(root_path.rglob("*.md")):
        if path.name == "SKILL.md" or _SKIP_DIRS & set(path.parts):
            continue
        if path.stem.upper() in _NON_SKILL_STEMS:
            continue
        if _inside_any(path, bundles):
            continue
        meta = parse_skill(path)
        found.setdefault(meta.name, meta)
    return sorted(found.values(), key=lambda s: s.name)


def skill_dir(meta: SkillMeta) -> Path:
    path = Path(meta.path)
    return path.parent if path.name == "SKILL.md" else path.parent
