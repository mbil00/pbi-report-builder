"""`pbi diff` runs apply on a temporary copy, so it reports what apply would do (#80)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from pbi.apply import apply_yaml
from pbi.apply.trial import json_changes, trial_apply
from pbi.project import Project
from pbi.styles import create_style
from tests.support import cli, make_project, pbip_path


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _exported(root: Path) -> dict[str, Any]:
    result = cli("export", project=root)
    assert result.exit_code == 0, result.output
    return yaml.safe_load(result.output)


def _visual(spec: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        visual
        for page in spec["pages"]
        for visual in page.get("visuals", [])
        if visual.get("name") == name
    )


def _write(path: Path, spec: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


def test_diff_reports_an_error_apply_would_raise(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy("report-02-model-heavy")
    spec = _exported(root)
    _visual(spec, "card-actual")["bindings"]["Values"] = "GL_Actuals.No Such Measure (measure)"
    spec_file = _write(tmp_path / "bad.yaml", spec)
    before = _snapshot(root)

    diff = cli("diff", spec_file, project=root)
    assert _snapshot(root) == before
    apply = cli("apply", spec_file, project=root)

    assert apply.exit_code == 1
    assert diff.exit_code == 1, diff.output
    assert "No differences found" not in diff.output
    errors = [line for line in apply.output.splitlines() if line.startswith("Error:")]
    assert errors
    for line in errors:
        assert line in diff.output
    assert _snapshot(root) == before


def test_diff_lists_the_files_and_json_paths_apply_would_change(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy("report-02-model-heavy")
    spec = _exported(root)
    card = _visual(spec, "card-actual")
    card["title"]["text"] = "Actuals"
    spec_file = _write(tmp_path / "title.yaml", spec)
    before = _snapshot(root)

    diff = cli("diff", spec_file, project=root)

    assert diff.exit_code == 0, diff.output
    assert _snapshot(root) == before
    visual_json = next(path for path in before if f"/visuals/{card['id']}/visual.json" in path)
    assert f"~ {visual_json}" in diff.output
    assert "visualContainerObjects.title[0].properties.text.expr.Literal.Value" in diff.output
    assert "\"'Actual Amount'\" -> \"'Actuals'\"" in diff.output
    assert "title.text: Actual Amount -> Actuals" in diff.output  # the property view

    cli("apply", spec_file, project=root)
    after = _snapshot(root)
    assert sorted(path for path in before if before[path] != after.get(path)) == [visual_json]


def test_diff_lists_files_a_new_visual_would_add(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    spec_file = _write(
        tmp_path / "new.yaml",
        {"pages": [{"name": "Demo", "visuals": [{"name": "box", "type": "shape"}]}]},
    )

    diff = cli("diff", spec_file, project=project)

    assert diff.exit_code == 0, diff.output
    assert "+ New page: Demo" in diff.output
    assert "+ Sample.Report/definition/pages/pages.json" in diff.output
    # Apply picks new folder IDs at random, so the trial's IDs are hidden.
    assert "+ Sample.Report/definition/pages/<new>/page.json" in diff.output
    assert "+ Sample.Report/definition/pages/<new>/visuals/<new>/visual.json" in diff.output
    assert diff.output.count("/visual.json") == 1
    assert not (project.definition_folder / "pages").exists()


def test_diff_keeps_existing_folder_ids_in_added_paths(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy("report-02-model-heavy")
    spec = _exported(root)
    spec["pages"][0]["visuals"].append({"name": "box", "type": "shape"})
    page_folder = Project.find(pbip_path(root)).find_page(spec["pages"][0]["name"]).folder.name

    diff = cli("diff", _write(tmp_path / "add.yaml", spec), project=root)

    assert diff.exit_code == 0, diff.output
    assert f"/pages/{page_folder}/visuals/<new>/visual.json" in diff.output


def _symlink_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are not available")


def test_diff_follows_a_symlinked_report_artifact(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "Sample.Report").rename(tmp_path / "report-files")
    _symlink_dir(tmp_path / "Sample.Report", Path("report-files"))
    spec_file = _write(tmp_path / "empty.yaml", {"pages": []})

    diff = cli("diff", spec_file, project=tmp_path)

    assert diff.exit_code == 0, diff.output
    assert "No differences found" in diff.output


def test_diff_follows_symlinked_resource_folders(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    shared = tmp_path / "shared-assets"
    shared.mkdir()
    (shared / "logo.png").write_bytes(b"png")
    resources = project.report_folder / "StaticResources"
    resources.mkdir()
    _symlink_dir(resources / "RegisteredResources", shared)
    spec_file = _write(tmp_path / "empty.yaml", {"pages": []})

    diff = cli("diff", spec_file, project=project)

    assert diff.exit_code == 0, diff.output
    assert "No differences found" in diff.output


def test_diff_resolves_project_styles(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    create_style(project, "framed", {"border.show": True})
    spec_file = _write(
        tmp_path / "styled.yaml",
        {"pages": [{"name": "Demo", "visuals": [{"name": "box", "type": "shape", "style": "framed"}]}]},
    )

    diff = cli("diff", spec_file, project=project)

    assert diff.exit_code == 0, diff.output
    assert "Error" not in diff.output


def test_diff_accepts_yaml_apply_accepts_without_pages(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    spec_file = _write(tmp_path / "empty.yaml", {"version": 1})

    assert cli("apply", spec_file, project=project).exit_code == 0
    diff = cli("diff", spec_file, project=project)

    assert diff.exit_code == 0, diff.output
    assert "No differences found" in diff.output


def test_trial_copy_leaves_out_desktop_cache_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_project(tmp_path, with_model=True)
    create_style(Project.find(pbip_path(tmp_path)), "framed", {"border.show": True})
    cache = tmp_path / "Sample.SemanticModel" / ".pbi"
    cache.mkdir()
    (cache / "cache.abf").write_bytes(b"\0" * 16)
    copied: list[Path] = []

    def recording_apply(project: Project, *args: Any, **kwargs: Any) -> Any:
        copied.extend(path.relative_to(project.root) for path in project.root.rglob("*"))
        return apply_yaml(project, *args, **kwargs)

    monkeypatch.setattr("pbi.apply.trial.apply_yaml", recording_apply)
    trial = trial_apply(Project.find(pbip_path(tmp_path)), "version: 1\n")

    assert trial.is_noop
    assert Path("Sample.SemanticModel/definition/tables/Customers.tmdl") in copied
    assert Path(".pbi-styles/framed.yaml") in copied
    assert not any(".pbi" in path.parts for path in copied)


def _changes(old: Any, new: Any) -> list[str]:
    out: list[str] = []
    json_changes(old, new, "", out)
    return out


def test_json_changes_reports_values_types_keys_and_order() -> None:
    assert _changes({"a": 1}, {"a": 1}) == []
    assert _changes({"a": 1}, {"a": 1.0}) == ["a: 1 -> 1.0"]
    assert _changes({"a": 1}, {"a": True}) == ["a: 1 -> true"]
    assert _changes({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ["(root): key order changed"]
    assert _changes({"a": {"b": 1}}, {"a": {"c": 1}}) == ["a.b: removed", "a.c: added"]
    assert _changes({"$schema": "x"}, {"$schema": "y"}) == ['["$schema"]: "x" -> "y"']
    assert _changes({"l": [1, 2]}, {"l": [1]}) == ["l[1]: removed"]
    assert _changes({"l": [1]}, {"l": [1, {}]}) == ["l[1]: added"]
    assert _changes({"l": [{"x": "a"}]}, {"l": [{"x": "b"}]}) == ['l[0].x: "a" -> "b"']
    assert _changes({"a": None}, {"a": {}}) == ["a: null -> {}"]


def test_diff_copies_a_report_inside_a_sidecar_folder_once(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / ".pbi-reports").mkdir()
    (tmp_path / "Sample.Report").rename(tmp_path / ".pbi-reports" / "Sample.Report")
    (tmp_path / "Sample.pbip").write_text(
        '{"artifacts": [{"report": {"path": ".pbi-reports/Sample.Report"}}]}\n', encoding="utf-8"
    )
    spec_file = _write(tmp_path / "empty.yaml", {"pages": []})

    diff = cli("diff", spec_file, project=tmp_path)

    assert diff.exit_code == 0, diff.output
    assert "No differences found" in diff.output
