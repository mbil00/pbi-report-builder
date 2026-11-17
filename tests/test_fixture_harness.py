"""Fixture harness: run the CLI over every committed PBIP fixture.

The Desktop-saved fixtures are the main validation target. Each fixture is
copied to a temporary folder (never edited in place) and run through:

1. ``validate`` and ``model check``: no errors, no schema warnings.
2. A read-only sweep of the project, page, visual and model-table commands.
3. Report round-trip: ``export`` then ``apply`` changes no bytes, and ``diff``
   agrees with ``apply``.
4. Model round-trip: ``model export`` then ``model apply`` changes no bytes.
5. Raw-payload guard: the number of visuals ``export`` falls back to raw
   ``pbir:`` for may only go down.
6. Comparisons with Desktop output: a measure rename against the Desktop
   rename snapshot, a theme round-trip on report-04, and the literal type
   ``visual set`` writes against the one Desktop wrote.

Known failures are ``xfail(strict=True)`` naming their issue, set in the
``KNOWN_*`` tables below. A fix removes its entries; a strict xfail that
starts passing fails the suite until it is removed.

report-03 was built with ``pbi``. It runs the round-trip and idempotency
steps, but is never ground truth for shapes (step 6 leaves it out).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from click.testing import CliRunner, Result

from pbi.model import SemanticModel
from pbi.project import Project
from tests.support import (
    FIXTURES,
    KITCHEN_SINK_DIR,
    RENAMED_DIR,
    SAMPLE_REPORT_DIR,
    SHAPES_DIR,
    pbip_path,
    read_json,
    report_definition,
)

FIXTURE_NAMES = list(FIXTURES)

# --- Known failures (fixture name -> issue) -----------------------------------

KNOWN_REPORT_ROUNDTRIP = {
    "report-01-kitchen-sink": "#108, #113",
    "report-04-desktop-shapes": "#108",
    "report-04-desktop-shapes-renamed": "#108",
    "sample-report": "#108, #109",
}

# Every fixture has a table without measures, so `model measure list --json`
# prints prose there.
KNOWN_LIST_JSON = {name: "#101" for name in FIXTURE_NAMES}

# Visuals that `export` writes as raw `pbir:` payloads. Lower a number when a
# fix shrinks it; it must never grow.
RAW_PBIR_BASELINE = {
    "report-01-kitchen-sink": 7,
    "report-02-model-heavy": 1,
    "report-03-authoring-parity-lab": 24,
    "report-04-desktop-shapes": 6,
    "report-04-desktop-shapes-renamed": 6,
    "sample-report": 6,
}

# `theme get` fails where the project has no usable custom theme.
THEME_GET_ERRORS = {
    "report-01-kitchen-sink": 'Theme file for "Contoso Retail" not found',
    "report-02-model-heavy": "No custom theme applied",
    "sample-report": "No custom theme applied",
}


def per_fixture(known: dict[str, str]) -> list[Any]:
    """Parametrize over every fixture, with a strict xfail where ``known`` names an issue."""
    return [
        pytest.param(
            name,
            id=name,
            marks=[pytest.mark.xfail(strict=True, reason=known[name])] if name in known else [],
        )
        for name in FIXTURE_NAMES
    ]


# --- Running the CLI ------------------------------------------------------------


@cache
def _command():
    from pbi.cli import app

    return typer.main.get_command(app)


def run(root: Path, *args: Any) -> Result:
    """Run ``pbi --project <root> <args>`` in-process.

    Reuses one built Click command: rebuilding it per call (as
    ``tests.support.cli`` does) costs ~30ms, which the per-visual sweep can't afford.
    """
    return CliRunner().invoke(_command(), ["--project", str(root), *map(str, args)])


def ok(result: Result, *args: Any) -> Result:
    detail = result.output.strip()
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        detail += f"\n{type(result.exception).__name__}: {result.exception}"
    assert result.exit_code == 0, f"pbi {' '.join(map(str, args))} exited {result.exit_code}:\n{detail}"
    return result


def run_ok(root: Path, *args: Any) -> Result:
    return ok(run(root, *args), *args)


# --- Tree snapshots -------------------------------------------------------------


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def changed_files(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))


def assert_unchanged(root: Path, before: dict[str, bytes], step: str) -> None:
    changed = changed_files(before, snapshot(root))
    assert not changed, f"{step} changed {len(changed)} file(s):\n" + "\n".join(changed)


# --- Project walkers ------------------------------------------------------------


def _pages_and_visuals(root: Path) -> Iterator[tuple[str, list[str]]]:
    project = Project.find(pbip_path(root))
    for page in project.get_pages():
        yield page.name, [visual.name for visual in project.get_visuals(page)]


def _tables(root: Path) -> list[str]:
    return [table["name"] for table in json.loads(run_ok(root, "model", "table", "list", "--json").output)]


# --- Step 1: validation -----------------------------------------------------------


@pytest.mark.parametrize("name", per_fixture({}))
def test_validate_clean(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    issues = json.loads(run_ok(root, "validate", "--json").output)
    errors = [issue for issue in issues if issue["level"] == "error"]
    schema_warnings = [
        issue for issue in issues if issue["level"] == "warning" and issue["message"].startswith("Schema:")
    ]
    assert errors == []
    assert schema_warnings == []


@pytest.mark.parametrize("name", per_fixture({}))
def test_model_check_has_no_errors(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    findings = json.loads(run_ok(root, "model", "check", "--json").output)
    assert [finding for finding in findings if finding["severity"] == "error"] == []


# --- Step 2: read-only sweep ------------------------------------------------------

PROJECT_COMMANDS = [
    ("map",),
    ("info",),
    ("page", "list", "--json"),
    ("bookmark", "list", "--json"),
    ("filter", "list", "--json"),
    ("image", "list", "--json"),
]


@pytest.mark.parametrize("name", per_fixture({}))
def test_project_read_commands(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    before = snapshot(root)
    for args in PROJECT_COMMANDS:
        run_ok(root, *args)

    for args in (("theme", "get"), ("theme", "get", "--json")):
        result = run(root, *args)
        if name in THEME_GET_ERRORS:
            assert result.exit_code == 1, result.output
            assert THEME_GET_ERRORS[name] in result.output
        else:
            ok(result, *args)
    assert_unchanged(root, before, "project read commands")


@pytest.mark.parametrize("name", per_fixture({}))
def test_page_and_visual_read_commands(fixture_copy: Callable[[str], Path], name: str, tmp_path: Path) -> None:
    root = fixture_copy(name)
    before = snapshot(root)
    html = tmp_path / "render.html"
    for page, visuals in _pages_and_visuals(root):
        run_ok(root, "page", "get", page)
        run_ok(root, "render", page, "-o", html)
        json.loads(run_ok(root, "visual", "list", page, "--json").output)
        for visual in visuals:
            run_ok(root, "visual", "get", page, visual, "--full")
            yaml.safe_load(run_ok(root, "visual", "export", page, visual).output)
    assert_unchanged(root, before, "page and visual read commands")


@pytest.mark.parametrize("name", per_fixture({}))
def test_model_table_read_commands(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    before = snapshot(root)
    for table in _tables(root):
        run_ok(root, "model", "column", "list", table, "--json")
        run_ok(root, "model", "measure", "list", table, "--json")
        run_ok(root, "model", "fields", table, "--json")
    assert_unchanged(root, before, "model table read commands")


@pytest.mark.parametrize("name", per_fixture(KNOWN_LIST_JSON))
def test_list_json_parses(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    commands = [args for args in PROJECT_COMMANDS if "--json" in args]
    for table in _tables(root):
        commands += [
            ("model", "column", "list", table, "--json"),
            ("model", "measure", "list", table, "--json"),
            ("model", "fields", table, "--json"),
        ]
    unparseable = []
    for args in commands:
        output = run_ok(root, *args).output
        try:
            json.loads(output)
        except json.JSONDecodeError:
            unparseable.append(f"pbi {' '.join(args)}: {output.strip()[:80]}")
    assert unparseable == []


# --- Step 3: report round-trip ----------------------------------------------------


def _export(root: Path, tmp_path: Path) -> Path:
    spec = tmp_path / "report.yaml"
    run_ok(root, "export", "-o", spec)
    return spec


@pytest.mark.parametrize("name", per_fixture(KNOWN_REPORT_ROUNDTRIP))
def test_report_roundtrip_is_noop(fixture_copy: Callable[[str], Path], name: str, tmp_path: Path) -> None:
    root = fixture_copy(name)
    spec = _export(root, tmp_path)
    before = snapshot(root)
    run_ok(root, "apply", spec)
    assert_unchanged(root, before, "export -> apply")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_diff_agrees_with_apply(fixture_copy: Callable[[str], Path], name: str, tmp_path: Path) -> None:
    root = fixture_copy(name)
    spec = _export(root, tmp_path)
    diff = run(root, "diff", spec)
    diff_clean = diff.exit_code == 0 and "No differences found" in diff.output

    before = snapshot(root)
    apply = run(root, "apply", spec)
    changed = changed_files(before, snapshot(root))
    apply_clean = apply.exit_code == 0 and not changed

    assert diff_clean == apply_clean, (
        f"diff says {'no differences' if diff_clean else 'differences'}; "
        f"apply exited {apply.exit_code} and changed {len(changed)} file(s)"
    )
    assert (diff.exit_code == 0) == (apply.exit_code == 0), diff.output
    assert diff_files(diff.output) == changed, diff.output


def diff_files(output: str) -> list[str]:
    """The files ``diff`` says apply would add (+), remove (-) or rewrite (~)."""
    return sorted(re.findall(r"^  [~+-] (\S.*)$", output, flags=re.MULTILINE))


# --- Step 4: model round-trip -----------------------------------------------------


@pytest.mark.parametrize("name", per_fixture({}))
def test_model_roundtrip_is_noop(fixture_copy: Callable[[str], Path], name: str, tmp_path: Path) -> None:
    root = fixture_copy(name)
    spec = tmp_path / "model.yaml"
    run_ok(root, "model", "export", "-o", spec)
    before = snapshot(root)
    run_ok(root, "model", "apply", spec)
    assert_unchanged(root, before, "model export -> model apply")


@pytest.mark.parametrize("name", ["report-04-desktop-shapes", "report-04-desktop-shapes-renamed"])
def test_changed_property_is_metadata(fixture_copy: Callable[[str], Path], name: str, tmp_path: Path) -> None:
    """``changedProperty`` is metadata, not DAX (#75).

    Desktop writes ``changedProperty = X`` under columns and tables. The model
    export leaves them out and keeps the calculated columns' DAX intact;
    ``test_model_roundtrip_is_noop`` checks that apply keeps the lines.
    """
    root = fixture_copy(name)
    tmdl = [line.strip() for path in root.rglob("*.tmdl") for line in path.read_text(encoding="utf-8-sig").splitlines()]
    assert sum(line.startswith("changedProperty") for line in tmdl) == 22

    spec = tmp_path / "model.yaml"
    run_ok(root, "model", "export", "-o", spec)
    assert "changedProperty" not in spec.read_text(encoding="utf-8")

    columns = {column.name: column.expression for column in SemanticModel.load(root).find_table("Task").columns}
    assert columns["Duration Band"] == (
        'SWITCH ( TRUE (), Task[Duration Days] <= 7, "Up to 1 week", Task[Duration Days] <= 14, "1-2 weeks", '
        'Task[Duration Days] <= 30, "2-4 weeks", "Over 4 weeks" )'
    )
    assert columns["Duration Band Order"] == (
        "SWITCH ( TRUE (), Task[Duration Days] <= 7, 1, Task[Duration Days] <= 14, 2, "
        "Task[Duration Days] <= 30, 3, 4 )"
    )


# --- Step 5: raw-payload guard ----------------------------------------------------


def _count_raw_visuals(node: Any) -> int:
    if isinstance(node, dict):
        return int("pbir" in node) + sum(_count_raw_visuals(value) for value in node.values())
    if isinstance(node, list):
        return sum(_count_raw_visuals(item) for item in node)
    return 0


@pytest.mark.parametrize("name", per_fixture({}))
def test_raw_pbir_fallbacks_do_not_grow(fixture_copy: Callable[[str], Path], name: str) -> None:
    root = fixture_copy(name)
    exported = yaml.safe_load(run_ok(root, "export").output)
    count = _count_raw_visuals(exported.get("pages", []))
    baseline = RAW_PBIR_BASELINE[name]
    assert count <= baseline, f"export fell back to raw pbir: for {count} visuals (baseline {baseline})"
    assert count == baseline, f"raw pbir: fallbacks dropped to {count}; lower RAW_PBIR_BASELINE[{name!r}]"


# --- Step 6: comparisons with Desktop output ----------------------------------------

RENAMED_MODEL_FILES = [
    pytest.param("tables/Measures Table.tmdl"),
    pytest.param("tables/Metric Selector.tmdl"),
    pytest.param("cultures/en-US.tmdl", marks=pytest.mark.xfail(strict=True, reason="#102")),
]


@pytest.mark.parametrize("model_file", RENAMED_MODEL_FILES)
def test_measure_rename_matches_desktop(fixture_copy: Callable[[str], Path], model_file: str) -> None:
    root = fixture_copy(SHAPES_DIR.name)
    run_ok(root, "model", "measure", "rename", "Measures Table", "Total Hours", "Hours Logged")
    definition = "04-desktop-shapes.SemanticModel/definition"
    assert (root / definition / model_file).read_bytes() == (RENAMED_DIR / definition / model_file).read_bytes()


@pytest.mark.xfail(strict=True, reason="#103")
def test_theme_roundtrip_is_noop(fixture_copy: Callable[[str], Path], tmp_path: Path) -> None:
    root = fixture_copy(SHAPES_DIR.name)
    theme = tmp_path / "theme.json"
    run_ok(root, "theme", "export", theme)
    before = snapshot(root)
    run_ok(root, "theme", "apply", theme)
    assert_unchanged(root, before, "theme export -> theme apply")


# Desktop-saved fixtures whose numeric visual literals are compared. report-01
# was partly edited by the CLI, but the CLI writes `1.0D`, never `1D`, so its
# integer-looking `D` literals are Desktop's.
LITERAL_FIXTURES = (KITCHEN_SINK_DIR, SHAPES_DIR, SAMPLE_REPORT_DIR)
NUMERIC_LITERAL = re.compile(r"^(-?\d+(?:\.\d+)?)([DLM])$")
KNOWN_LITERAL_MISMATCHES = {
    ("report-01-kitchen-sink", "cardVisual", "objects", "layout", "cellPadding"): "#104",
    ("report-01-kitchen-sink", "cardVisual", "objects", "layout", "columnCount"): "#104",
    ("report-01-kitchen-sink", "cardVisual", "objects", "value", "fontSize"): "#104",
    ("report-04-desktop-shapes", "cardVisual", "objects", "value", "fontSize"): "#104",
}


def _literal(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("expr", {}).get("Literal", {}).get("Value")
    return None


@cache
def _literal_cases() -> list[Any]:
    """One case per (fixture, visual type, container, object, property) with a numeric literal."""
    cases: dict[tuple[str, ...], Any] = {}
    for root in LITERAL_FIXTURES:
        definition = report_definition(root)
        for path in sorted(definition.glob("pages/*/visuals/*/visual.json")):
            visual = read_json(path).get("visual")
            if visual is None:  # visual group
                continue
            for container in ("objects", "visualContainerObjects"):
                for obj, entries in visual.get(container, {}).items():
                    for entry in entries:
                        for prop, value in entry.get("properties", {}).items():
                            literal = _literal(value)
                            if not (isinstance(literal, str) and NUMERIC_LITERAL.match(literal)):
                                continue
                            key = (root.name, visual["visualType"], container, obj, prop)
                            if key in cases:
                                continue
                            marks = (
                                [pytest.mark.xfail(strict=True, reason=KNOWN_LITERAL_MISMATCHES[key])]
                                if key in KNOWN_LITERAL_MISMATCHES
                                else []
                            )
                            cases[key] = pytest.param(
                                *key, path.relative_to(definition).as_posix(), literal,
                                id=f"{root.name}:{key[1]}.{obj}.{prop}", marks=marks,
                            )
    return list(cases.values())


@pytest.mark.parametrize("fixture,visual_type,container,obj,prop,visual_file,desktop", _literal_cases())
def test_literal_suffix_matches_desktop(
    fixture_copy: Callable[[str], Path],
    fixture: str,
    visual_type: str,
    container: str,
    obj: str,
    prop: str,
    visual_file: str,
    desktop: str,
) -> None:
    """``visual set`` writes the literal type (``D``/``L``/``M``) Desktop wrote for the same property."""
    root = fixture_copy(fixture)
    path = report_definition(root) / visual_file
    data = read_json(path)
    for entry in data["visual"][container][obj]:
        entry.get("properties", {}).pop(prop, None)
    path.write_text(json.dumps(data), encoding="utf-8")

    number, suffix = NUMERIC_LITERAL.match(desktop).groups()
    key = f"chart:{obj}.{prop}" if container == "objects" else f"{obj}.{prop}"
    page, visual = path.parent.parent.parent.name, path.parent.name
    run_ok(root, "visual", "set", page, visual, f"{key}={number}")

    written = [
        _literal(entry["properties"][prop])
        for entry in read_json(path)["visual"].get(container, {}).get(obj, [])
        if prop in entry.get("properties", {})
    ]
    assert written, f"visual set wrote no {obj}.{prop}"
    for literal in written:
        match = NUMERIC_LITERAL.match(literal) if isinstance(literal, str) else None
        assert match is not None, f"{obj}.{prop}: wrote {literal!r}, Desktop wrote {desktop!r}"
        assert match.group(2) == suffix, f"{obj}.{prop}: wrote {literal!r}, Desktop wrote {desktop!r}"
        assert float(match.group(1)) == float(number)
