"""Discover and parse SKILL.md files across a skill library."""

from __future__ import annotations

import os
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


def _depth_key(item: tuple[Path, SkillMeta]) -> tuple[int, Path]:
    return len(item[0].parts), item[0]


def discover_skills(root: str | Path) -> list[SkillMeta]:
    """Find every skill under ``root``.

    Two layouts count: a bundle directory (``<name>/SKILL.md``) and a flat file
    (``<name>.md``). Plugin trees nest skills arbitrarily deep, so the search is
    recursive, with three rules that keep it from inventing skills:

    * Everything inside a bundle belongs to that bundle. Its ``references/``,
      ``examples/`` and notes are files it ships, and a ``SKILL.md`` nested
      under it is a worked example, not a skill of its own.
    * A flat ``.md`` counts only if it declares itself with YAML frontmatter.
      A filename cannot say "this is a skill" the way ``SKILL.md`` does, so
      without that declaration an ADR or a scratch note would become a skill
      that fails every check a real one passes. ``SKILL.md`` itself is exempt,
      so lint still reports a bundle that forgot its frontmatter.
    * The root's own ``SKILL.md`` does not claim the tree beneath it. Pointing
      at a single bundle yields that one skill; pointing at a library that also
      holds a stray ``SKILL.md`` must not hide every skill under it.

    When two skills declare the same name, the bundle wins over the flat file
    and the shallowest wins over the deeper one, so the result does not depend
    on traversal order.
    """
    root_path = Path(root)
    if root_path.is_file():
        return [parse_skill(root_path)]
    if not root_path.is_dir():
        raise FileNotFoundError(f"skills directory not found: {root_path}")

    bundles: list[tuple[Path, SkillMeta]] = []
    flats: list[tuple[Path, SkillMeta]] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        current = Path(dirpath)
        # Prune rather than filter afterwards: these trees are large and the
        # names are matched below the root, so a root that merely *lives* under
        # one of them (a checkout inside .venv, say) still discovers its skills.
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)

        if "SKILL.md" in filenames:
            path = current / "SKILL.md"
            bundles.append((path, parse_skill(path)))
            if current != root_path:
                dirnames[:] = []
                continue

        for name in sorted(filenames):
            if name == "SKILL.md" or not name.endswith(".md"):
                continue
            path = current / name
            if path.stem.upper() in _NON_SKILL_STEMS:
                continue
            meta = parse_skill(path)
            if not meta.frontmatter:
                continue
            flats.append((path, meta))

    found: dict[str, SkillMeta] = {}
    for _path, meta in sorted(bundles, key=_depth_key) + sorted(flats, key=_depth_key):
        found.setdefault(meta.name, meta)
    return sorted(found.values(), key=lambda s: s.name)


def skill_dir(meta: SkillMeta) -> Path:
    """The directory a skill's relative references resolve against."""
    return Path(meta.path).parent
