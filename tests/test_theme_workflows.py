from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.project import Project
from pbi.themes import (
    apply_theme_data,
    create_and_apply_theme,
    create_theme,
    get_theme_data,
    update_theme_properties,
)
from tests.test_themes import _scaffold_project


def test_apply_theme_data_writes_registered_theme_file_and_report_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pbip = _scaffold_project(Path(tmp))
        project = Project.find(pbip)

        name = apply_theme_data(project, create_theme("Brand", foreground="#333333"))
        assert name == "Brand"

        report = json.loads((project.definition_folder / "report.json").read_text(encoding="utf-8-sig"))
        assert report["themeCollection"]["customTheme"]["name"] == "Brand.json"
        items = report["resourcePackages"][0]["items"]
        assert items[0]["type"] == "CustomTheme"
        assert items[0]["path"] == "Brand.json"

        theme_path = project.report_folder / "StaticResources" / "RegisteredResources" / "Brand.json"
        assert theme_path.exists()
        theme_data = json.loads(theme_path.read_text(encoding="utf-8-sig"))
        assert theme_data["name"] == "Brand"


def test_create_and_apply_theme_replaces_old_custom_theme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pbip = _scaffold_project(Path(tmp), theme_data=create_theme("OldTheme"))
        project = Project.find(pbip)

        name = create_and_apply_theme(project, "NewTheme", foreground="#111111", accent="#0078D4")
        assert name == "NewTheme"

        report = json.loads((project.definition_folder / "report.json").read_text(encoding="utf-8-sig"))
        assert report["themeCollection"]["customTheme"]["name"] == "NewTheme.json"
        old_path = project.report_folder / "StaticResources" / "RegisteredResources" / "OldTheme.json"
        new_path = project.report_folder / "StaticResources" / "RegisteredResources" / "NewTheme.json"
        assert not old_path.exists()
        assert new_path.exists()


def test_update_theme_properties_returns_structured_changes_and_persists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pbip = _scaffold_project(Path(tmp), theme_data=create_theme("Active"))
        project = Project.find(pbip)

        changes = update_theme_properties(
            project,
            [("foreground", "#111111"), ("textClasses.title.fontSize", "14")],
        )

        assert [change.prop for change in changes] == ["foreground", "textClasses.title.fontSize"]
        assert changes[0].changed is True
        assert "foregroundDark" in changes[0].cascaded_keys
        assert changes[1].changed is True

        reloaded = get_theme_data(project)
        assert reloaded["foreground"] == "#111111"
        assert reloaded["textClasses"]["title"]["fontSize"] == 14
