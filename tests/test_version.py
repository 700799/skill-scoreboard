"""The package declares its version twice; they must not drift.

`skill-scoreboard --version` reads ``__version__`` while PyPI and the publish
workflow's tag guard read ``pyproject.toml``. Bumping one and forgetting the
other ships a CLI that misreports itself, and the tag guard still passes.
"""

import tomllib
from pathlib import Path

import skill_scoreboard

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_declared_version_matches_pyproject() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert skill_scoreboard.__version__ == project
