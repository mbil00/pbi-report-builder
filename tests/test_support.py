"""Tests for the shared test support in ``tests/support.py`` and ``tests/conftest.py``."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from pbi.project import Project
from tests.support import (
    FIXTURES,
    SHAPES_DIR,
    assert_project_trees_equivalent,
    cli,
    copy_fixture,
    pbip_path,
)

TESTS_DIR = Path(__file__).resolve().parent


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_copy_leaves_out_build_inputs_and_opens(fixture_copy, name: str) -> None:
    copy = fixture_copy(name)

    assert copy.name == name
    assert not (copy / "data").exists()
    assert not list(copy.rglob("*.md"))
    project = Project.find(pbip_path(copy))
    assert project.root == copy
    assert project.get_pages()


def test_fixture_copy_keeps_everything_else(tmp_path: Path) -> None:
    copy = copy_fixture(SHAPES_DIR.name, tmp_path)

    expected = sorted(
        path.relative_to(SHAPES_DIR)
        for path in SHAPES_DIR.rglob("*")
        if path.is_file() and path.suffix != ".md" and path.relative_to(SHAPES_DIR).parts[0] != "data"
    )
    assert sorted(path.relative_to(copy) for path in copy.rglob("*") if path.is_file()) == expected


def test_copy_fixture_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="Available"):
        copy_fixture("report-99", tmp_path)


def test_fixture_project_opens_a_copy(fixture_project, tmp_path: Path) -> None:
    project = fixture_project("sample-report")

    assert project.root.parent == tmp_path


def test_cli_passes_project(tmp_project: Project) -> None:
    result = cli("page", "create", "Overview", project=tmp_project)
    assert result.exit_code == 0, result.output

    listed = cli("page", "list", "--json", project=tmp_project.root)
    assert listed.exit_code == 0, listed.output
    assert [row["name"] for row in json.loads(listed.output)] == ["Overview"]


def test_assert_project_trees_equivalent(fixture_copy, tmp_path: Path) -> None:
    left = fixture_copy("sample-report")
    right = copy_fixture("sample-report", tmp_path / "other")

    assert_project_trees_equivalent(None, left, right)

    page = next((right / "SampleReport.Report" / "definition" / "pages").glob("*/page.json"))
    data = json.loads(page.read_text(encoding="utf-8"))
    page.write_text(json.dumps(data, indent=4), encoding="utf-8")
    assert_project_trees_equivalent(None, left, right)

    data["displayName"] = "Changed"
    page.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssertionError, match="JSON differs"):
        assert_project_trees_equivalent(None, left, right)


def test_no_test_module_imports_another_test_module() -> None:
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                if module.split(".")[-1].startswith("test_"):
                    offenders.append(f"{path.name}:{node.lineno} imports {module}")
    assert offenders == [], "import shared helpers from tests.support instead"
