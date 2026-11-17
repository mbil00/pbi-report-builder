"""Pytest fixtures over the plain helpers in ``tests/support.py``.

``unittest.TestCase`` classes can't take pytest fixtures; they call the
helpers in ``tests.support`` directly with their own temporary directory.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pbi.project import Project
from tests.support import copy_fixture, load_fixture_project, make_project


@pytest.fixture
def fixture_copy(tmp_path: Path) -> Callable[[str], Path]:
    """Return ``copy(name)``: copy a fixture into ``tmp_path`` without ``data/`` and ``*.md``."""

    def copy(name: str) -> Path:
        return copy_fixture(name, tmp_path)

    return copy


@pytest.fixture
def fixture_project(tmp_path: Path) -> Callable[[str], Project]:
    """Return ``open(name)``: copy a fixture into ``tmp_path`` and open it as a ``Project``."""

    def open_project(name: str) -> Project:
        return load_fixture_project(name, tmp_path)

    return open_project


@pytest.fixture
def tmp_project(tmp_path: Path) -> Project:
    """A minimal hand-built ``Sample.pbip`` project in ``tmp_path``."""
    return make_project(tmp_path)
