from __future__ import annotations

import tomllib
from pathlib import Path

from pymini import __version__


def test_runtime_version_matches_package_metadata() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert metadata["tool"]["poetry"]["version"] == __version__
