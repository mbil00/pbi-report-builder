"""Shared test support: fixture paths, fixture copies, project scaffolds, CLI runner.

Plain helpers live here so both ``unittest.TestCase`` classes and pytest tests
can use them. ``tests/conftest.py`` wraps the tmp-path ones as pytest fixtures.
Test modules import helpers from here, never from another test module.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from click.testing import Result
from typer.testing import CliRunner

from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA

# --- Fixture paths -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
FIXTURE_ROOT = FIXTURES_DIR / "real-report-fixtures"

KITCHEN_SINK_DIR = FIXTURE_ROOT / "report-01-kitchen-sink"
MODEL_HEAVY_DIR = FIXTURE_ROOT / "report-02-model-heavy"
PARITY_LAB_DIR = FIXTURE_ROOT / "report-03-authoring-parity-lab"
SHAPES_DIR = FIXTURE_ROOT / "report-04-desktop-shapes"
SHAPES_DATA = SHAPES_DIR / "data"
SHAPES_PBIP = SHAPES_DIR / "04-desktop-shapes.pbip"
RENAMED_DIR = FIXTURE_ROOT / "report-04-desktop-shapes-renamed"
SAMPLE_REPORT_DIR = FIXTURES_DIR / "sample-report"

FIXTURES: dict[str, Path] = {
    path.name: path
    for path in (
        KITCHEN_SINK_DIR,
        MODEL_HEAVY_DIR,
        PARITY_LAB_DIR,
        SHAPES_DIR,
        RENAMED_DIR,
        SAMPLE_REPORT_DIR,
    )
}
"""Fixture projects by folder name. report-03 was built with ``pbi``, not Desktop."""


# --- Fixture copies ----------------------------------------------------------


def _ignore_build_inputs(source_root: Path):
    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name.endswith(".md")}
        if Path(directory) == source_root and "data" in names:
            ignored.add("data")
        return ignored

    return ignore


def copy_fixture(name: str, dest: Path) -> Path:
    """Copy fixture ``name`` into ``dest/<name>`` and return the copy's folder.

    The top-level ``data/`` folder (CSV build inputs) and Markdown notes are
    left out. Fixtures are never edited in place; tests work on the copy.
    """
    try:
        source = FIXTURES[name]
    except KeyError:
        raise KeyError(f"Unknown fixture {name!r}. Available: {', '.join(sorted(FIXTURES))}") from None
    target = Path(dest) / name
    shutil.copytree(source, target, ignore=_ignore_build_inputs(source))
    return target


def pbip_path(project_dir: Path) -> Path:
    """Return the single ``*.pbip`` file in ``project_dir``."""
    matches = sorted(Path(project_dir).glob("*.pbip"))
    if len(matches) != 1:
        raise AssertionError(f"expected one .pbip in {project_dir}, found {len(matches)}")
    return matches[0]


def load_fixture_project(name: str, dest: Path) -> Project:
    """Copy fixture ``name`` into ``dest`` and open it."""
    return Project.find(pbip_path(copy_fixture(name, dest)))


# --- Hand-built projects -----------------------------------------------------


def make_project(root: Path, *, with_model: bool = False) -> Project:
    """Scaffold a minimal ``Sample.pbip`` project (no pages, no base theme)."""
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps(
            {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {},
                "layoutOptimization": "None",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if with_model:
        tables = root / "Sample.SemanticModel" / "definition" / "tables"
        tables.mkdir(parents=True)
        (tables / "Customers.tmdl").write_text(
            "\n".join(
                [
                    "table 'Customers'",
                    "    column 'Region'",
                    "        dataType: string",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return Project.find(pbip)


def write_model_table(root: Path, filename: str, content: str) -> Path:
    """Write a table TMDL file into the test semantic model."""
    tables = root / "Sample.SemanticModel" / "definition" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / filename
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def make_themed_project(root: Path, *, theme_data: dict | None = None) -> Path:
    """Scaffold a minimal ``Test.pbip`` project with a base theme.

    With ``theme_data``, the theme is registered as the custom theme. Returns
    the ``.pbip`` path.
    """
    pbip_file = root / "Test.pbip"
    report_folder = root / "Test.Report"
    definition = report_folder / "definition"
    definition.mkdir(parents=True)

    pbip_file.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Test.Report"}}]}) + "\n",
        encoding="utf-8",
    )

    report: dict = {
        "$schema": REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {
                "name": "CY26SU02",
                "reportVersionAtImport": {"visual": "2.6.0", "report": "3.1.0", "page": "2.3.0"},
                "type": "SharedResources",
            },
        },
    }

    if theme_data:
        theme_name = theme_data.get("name", "TestTheme")
        resources_dir = report_folder / "StaticResources" / "RegisteredResources"
        resources_dir.mkdir(parents=True)
        theme_file = resources_dir / f"{theme_name}.json"
        theme_file.write_text(
            json.dumps(theme_data, indent=2), encoding="utf-8",
        )
        report["themeCollection"]["customTheme"] = {
            "name": theme_name,
            "reportVersionAtImport": {"visual": "2.6.0", "report": "3.1.0", "page": "2.3.0"},
            "type": "RegisteredResources",
        }
        report["resourcePackages"] = [
            {
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"type": "CustomTheme", "name": f"{theme_name}.json", "path": f"{theme_name}.json"}],
            }
        ]

    (definition / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )

    return pbip_file


# --- CLI ---------------------------------------------------------------------


def cli(*args: Any, project: Path | Project | None = None, **invoke_kwargs: Any) -> Result:
    """Run ``pbi <args>`` in-process and return the click ``Result``.

    ``project`` (a folder, ``.pbip`` path or ``Project``) is passed as the
    root-level ``--project`` option. Extra keyword arguments (``input``,
    ``env``, ``catch_exceptions``) go to ``CliRunner.invoke``.
    """
    from pbi.cli import app

    argv = [str(arg) for arg in args]
    if project is not None:
        root = project.root if isinstance(project, Project) else project
        argv = ["--project", str(root), *argv]
    return CliRunner().invoke(app, argv, **invoke_kwargs)


# --- PBIR readers (Desktop fixtures identify visuals by title) ----------------


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def literal_value(value: object) -> object:
    """Unwrap ``{"expr": {"Literal": {"Value": x}}}`` to ``x``."""
    if isinstance(value, dict):
        return value.get("expr", value).get("Literal", {}).get("Value")
    return None


def visual_title(visual: dict) -> str | None:
    """Return a visual's title text, or None when it has none."""
    containers = visual.get("visual", {}).get("visualContainerObjects", {})
    for entry in containers.get("title", []):
        text = literal_value(entry.get("properties", {}).get("text"))
        if isinstance(text, str):
            return text.strip("'")
    return None


def report_definition(root: Path = SHAPES_DIR) -> Path:
    """Return the ``*.Report/definition`` folder of the project in ``root``."""
    matches = sorted(Path(root).glob("*.Report/definition"))
    if len(matches) != 1:
        raise AssertionError(f"expected one *.Report/definition in {root}, found {len(matches)}")
    return matches[0]


def page_folders(root: Path = SHAPES_DIR) -> dict[str, Path]:
    """Map page display name to page folder, in page order."""
    pages_dir = report_definition(root) / "pages"
    order = read_json(pages_dir / "pages.json")["pageOrder"]
    return {read_json(pages_dir / pid / "page.json")["displayName"]: pages_dir / pid for pid in order}


def page_visuals(page: str, root: Path = SHAPES_DIR) -> list[dict]:
    """Return the parsed ``visual.json`` of every visual on ``page``."""
    folder = page_folders(root)[page] / "visuals"
    return [read_json(path / "visual.json") for path in sorted(folder.iterdir())]


def visual_by_title(page: str, title: str, root: Path = SHAPES_DIR) -> dict:
    """Return the one visual on ``page`` whose title is ``title``."""
    matches = [v for v in page_visuals(page, root) if visual_title(v) == title]
    if len(matches) != 1:
        raise AssertionError(f"expected one visual titled {title!r} on {page!r}, found {len(matches)}")
    return matches[0]


def visual_objects(visual: dict, name: str) -> list[dict]:
    """Return the entries of chart object ``name`` (``visual.objects.<name>``)."""
    return visual["visual"].get("objects", {}).get(name, [])


# --- Assertions --------------------------------------------------------------


def assert_project_trees_equivalent(testcase: Any, left: Path, right: Path) -> None:
    """Assert two PBIP project trees hold the same files with the same content.

    JSON files are compared by parsed content so formatting does not matter.
    All other files are compared byte-for-byte. ``testcase`` is any object with
    ``assertEqual`` (a ``unittest.TestCase``); pass ``None`` from pytest tests.
    """
    check = testcase.assertEqual if testcase is not None else _assert_equal

    left_files = _relative_files(left)
    right_files = _relative_files(right)
    check(right_files, left_files)

    for rel_path in left_files:
        left_file = left / rel_path
        right_file = right / rel_path
        if rel_path.suffix == ".json":
            check(read_json(left_file), read_json(right_file), f"JSON differs: {rel_path}")
        else:
            check(left_file.read_bytes(), right_file.read_bytes(), f"File differs: {rel_path}")


def _assert_equal(first: Any, second: Any, msg: str | None = None) -> None:
    assert first == second, msg


def _relative_files(root: Path) -> list[Path]:
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
