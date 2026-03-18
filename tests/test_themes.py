"""Tests for theme authoring: create, get, set, properties."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.schema_refs import REPORT_SCHEMA
from pbi.themes import (
    THEME_CASCADE,
    ThemePreset,
    _blend,
    _load_theme_preset,
    _validate_hex_color,
    clone_theme_preset,
    create_theme,
    delete_theme_preset,
    dump_theme_preset,
    get_theme_preset,
    get_theme_property,
    list_theme_presets,
    save_theme_preset,
    set_theme_property,
)


def _scaffold_project(root: Path, *, theme_data: dict | None = None) -> Path:
    """Create a minimal PBIP project. Optionally apply a custom theme."""
    pbip_path = root / "Test.pbip"
    report_folder = root / "Test.Report"
    definition = report_folder / "definition"
    definition.mkdir(parents=True)

    pbip_path.write_text(
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
                "items": [{"type": "CustomTheme", "name": theme_name, "path": f"{theme_name}.json"}],
            }
        ]

    (definition / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )

    return pbip_path


class TestValidateHexColor(unittest.TestCase):
    def test_valid_6_digit(self) -> None:
        self.assertEqual(_validate_hex_color("#aabbcc"), "#AABBCC")

    def test_valid_3_digit_expands(self) -> None:
        self.assertEqual(_validate_hex_color("#abc"), "#AABBCC")

    def test_valid_8_digit(self) -> None:
        self.assertEqual(_validate_hex_color("#aabbccdd"), "#AABBCCDD")

    def test_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            _validate_hex_color("red")
        with self.assertRaises(ValueError):
            _validate_hex_color("#GG0000")
        with self.assertRaises(ValueError):
            _validate_hex_color("123456")


class TestBlend(unittest.TestCase):
    def test_ratio_1_returns_first(self) -> None:
        self.assertEqual(_blend("#FF0000", "#0000FF", 1.0), "#FF0000")

    def test_ratio_0_returns_second(self) -> None:
        self.assertEqual(_blend("#FF0000", "#0000FF", 0.0), "#0000FF")

    def test_midpoint(self) -> None:
        result = _blend("#FF0000", "#0000FF", 0.5)
        # Should be approximately #7F007F
        self.assertTrue(result.startswith("#"))
        self.assertEqual(len(result), 7)


class TestCascade(unittest.TestCase):
    def test_foreground_cascades_4_derived(self) -> None:
        data = {"foreground": "#000000", "name": "test"}
        keys = set_theme_property(data, "foreground", "#111111", cascade=True)
        self.assertIn("foreground", keys)
        self.assertIn("foregroundDark", keys)
        self.assertIn("foregroundNeutralDark", keys)
        self.assertIn("foregroundSelected", keys)
        self.assertIn("backgroundDark", keys)
        self.assertEqual(len(keys), 5)
        # All derived should have the same value
        for derived in THEME_CASCADE["foreground"]:
            self.assertEqual(data[derived], "#111111")

    def test_no_cascade_skips_derived(self) -> None:
        data = {"foreground": "#000000", "name": "test"}
        keys = set_theme_property(data, "foreground", "#111111", cascade=False)
        self.assertEqual(keys, ["foreground"])
        self.assertNotIn("foregroundDark", data)

    def test_nested_property_does_not_cascade(self) -> None:
        data = {"foreground": "#000000", "textClasses": {"title": {"color": "#000"}}}
        keys = set_theme_property(data, "textClasses.title.color", "#222222", cascade=True)
        self.assertEqual(keys, ["textClasses.title.color"])


class TestGetThemeProperty(unittest.TestCase):
    def test_top_level(self) -> None:
        data = {"foreground": "#333", "name": "test"}
        self.assertEqual(get_theme_property(data, "foreground"), "#333")

    def test_nested(self) -> None:
        data = {"textClasses": {"title": {"fontSize": 12}}}
        self.assertEqual(get_theme_property(data, "textClasses.title.fontSize"), 12)

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(get_theme_property({}, "foo.bar"))


class TestSetThemeProperty(unittest.TestCase):
    def test_set_data_colors(self) -> None:
        data: dict = {}
        keys = set_theme_property(data, "dataColors", "#FF0000,#00FF00,#0000FF")
        self.assertEqual(keys, ["dataColors"])
        self.assertEqual(data["dataColors"], ["#FF0000", "#00FF00", "#0000FF"])

    def test_set_number(self) -> None:
        data: dict = {"textClasses": {"title": {"fontSize": 10}}}
        set_theme_property(data, "textClasses.title.fontSize", "14")
        self.assertEqual(data["textClasses"]["title"]["fontSize"], 14)

    def test_set_color_validates(self) -> None:
        data: dict = {}
        with self.assertRaises(ValueError):
            set_theme_property(data, "foreground", "not-a-color")


class TestCreateTheme(unittest.TestCase):
    def test_minimal(self) -> None:
        theme = create_theme("Brand")
        self.assertEqual(theme["name"], "Brand")
        self.assertEqual(theme["foreground"], "#252423")
        self.assertEqual(theme["background"], "#FFFFFF")
        self.assertEqual(theme["tableAccent"], "#118DFF")
        self.assertIn("textClasses", theme)
        self.assertIn("dataColors", theme)

    def test_with_all_options(self) -> None:
        theme = create_theme(
            "Full",
            foreground="#111111",
            background="#FAFAFA",
            accent="#0078D4",
            font="Inter",
            data_colors=["#0078D4", "#E94560"],
            good="#00AA00",
            bad="#DD0000",
            neutral="#CCAA00",
        )
        self.assertEqual(theme["foreground"], "#111111")
        self.assertEqual(theme["background"], "#FAFAFA")
        self.assertEqual(theme["tableAccent"], "#0078D4")
        self.assertEqual(theme["good"], "#00AA00")
        self.assertEqual(theme["bad"], "#DD0000")
        self.assertEqual(theme["neutral"], "#CCAA00")
        self.assertEqual(theme["dataColors"], ["#0078D4", "#E94560"])
        # Font should propagate to text classes
        self.assertIn("Inter", theme["textClasses"]["label"]["fontFace"])

    def test_cascade_derived_colors(self) -> None:
        theme = create_theme("Test", foreground="#333333")
        self.assertEqual(theme["foregroundDark"], "#333333")
        self.assertEqual(theme["foregroundNeutralDark"], "#333333")
        self.assertEqual(theme["foregroundSelected"], "#333333")
        self.assertEqual(theme["backgroundDark"], "#333333")

    def test_invalid_color_raises(self) -> None:
        with self.assertRaises(ValueError):
            create_theme("Bad", foreground="notacolor")


class TestThemeCreateCommand(unittest.TestCase):
    def test_dry_run_prints_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, [
            "theme", "create", "DryTest",
            "--foreground=#333333",
            "--accent=#0078D4",
            "--dry-run",
        ])
        self.assertEqual(result.exit_code, 0, result.stdout)
        output = json.loads(result.stdout)
        self.assertEqual(output["name"], "DryTest")
        self.assertEqual(output["foreground"], "#333333")

    def test_create_and_apply(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "create", "MyBrand",
                "--foreground=#222222",
                "--background=#FEFEFE",
                "--accent=#0078D4",
                "--font=Arial",
                "--data-colors=#0078D4,#E94560",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("MyBrand", result.stdout)

            # Verify theme was applied
            report = json.loads((Path(tmp) / "Test.Report" / "definition" / "report.json").read_text())
            self.assertEqual(report["themeCollection"]["customTheme"]["name"], "MyBrand")

            # Verify theme file exists
            theme_file = Path(tmp) / "Test.Report" / "StaticResources" / "RegisteredResources" / "MyBrand.json"
            self.assertTrue(theme_file.exists())
            theme = json.loads(theme_file.read_text())
            self.assertEqual(theme["foreground"], "#222222")


class TestThemeGetCommand(unittest.TestCase):
    def test_overview(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme", foreground="#333333", accent="#0078D4")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, ["theme", "get", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#333333", result.stdout)
            self.assertIn("TestTheme", result.stdout)

    def test_specific_property(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme", foreground="#444444")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, ["theme", "get", "foreground", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#444444", result.stdout)

    def test_raw_dumps_json(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, ["theme", "get", "--raw", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed["name"], "TestTheme")

    def test_no_theme_errors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, ["theme", "get", "-p", str(pbip)])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("No custom theme", result.stdout)


class TestThemeSetCommand(unittest.TestCase):
    def test_set_foreground_roundtrip(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme", foreground="#333333")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "foreground=#111111", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#111111", result.stdout)

            # Verify round-trip
            result = runner.invoke(app, ["theme", "get", "foreground", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#111111", result.stdout)

    def test_set_data_colors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "dataColors=#FF0000,#00FF00", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify
            result = runner.invoke(app, ["theme", "get", "dataColors", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#FF0000", result.stdout)

    def test_set_text_class_property(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "textClasses.title.fontSize=16", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)

            # Read back
            theme_file = Path(tmp) / "Test.Report" / "StaticResources" / "RegisteredResources" / "TestTheme.json"
            theme = json.loads(theme_file.read_text())
            self.assertEqual(theme["textClasses"]["title"]["fontSize"], 16)

    def test_set_cascade_shows_derived(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "foreground=#111111", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("cascaded", result.stdout)

    def test_set_no_cascade(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "foreground=#111111", "--no-cascade", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertNotIn("cascaded", result.stdout)

    def test_invalid_color_errors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            result = runner.invoke(app, [
                "theme", "set", "foreground=red", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Error", result.stdout)

    def test_no_theme_errors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "set", "foreground=#111111", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("No custom theme", result.stdout)


class TestThemePropertiesCommand(unittest.TestCase):
    def test_lists_properties(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["theme", "properties"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("foreground", result.stdout)
        self.assertIn("dataColors", result.stdout)
        self.assertIn("textClasses.title.fontSize", result.stdout)


# ── Theme preset storage tests ──────────────────────────────────────────


class TestSaveThemePreset(unittest.TestCase):
    def test_save_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            data = create_theme("Brand")
            path = save_theme_preset(proj, "brand", data)
            self.assertTrue(path.exists())
            self.assertIn(".pbi-themes", str(path))

    def test_save_global_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = create_theme("Global")
            global_dir = Path(tmp) / "themes"
            # Monkey-patch global dir
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                path = save_theme_preset(None, "corp", data, global_scope=True)
                self.assertTrue(path.exists())
                self.assertIn(str(global_dir), str(path))
            finally:
                themes_mod._global_themes_dir = orig

    def test_save_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            data = create_theme("Brand")
            save_theme_preset(proj, "brand", data)
            with self.assertRaises(FileExistsError):
                save_theme_preset(proj, "brand", data)

    def test_save_overwrite_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            data = create_theme("Brand")
            save_theme_preset(proj, "brand", data)
            path = save_theme_preset(proj, "brand", data, overwrite=True)
            self.assertTrue(path.exists())


class TestGetThemePreset(unittest.TestCase):
    def test_get_project_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            data = create_theme("Brand", foreground="#111111")
            save_theme_preset(proj, "brand", data)
            preset = get_theme_preset(proj, "brand")
            self.assertEqual(preset.name, "brand")
            self.assertEqual(preset.scope, "project")
            self.assertEqual(preset.data["foreground"], "#111111")

    def test_get_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            with self.assertRaises(FileNotFoundError):
                get_theme_preset(proj, "nonexistent")

    def test_get_falls_back_to_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            data = create_theme("GlobalTheme")
            global_dir = Path(tmp) / "global_themes"
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                save_theme_preset(None, "corp", data, global_scope=True)
                preset = get_theme_preset(proj, "corp")
                self.assertEqual(preset.scope, "global")
            finally:
                themes_mod._global_themes_dir = orig


class TestListThemePresets(unittest.TestCase):
    def test_list_merges_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)

            save_theme_preset(proj, "local-theme", create_theme("Local"))

            global_dir = Path(tmp) / "global_themes"
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                save_theme_preset(None, "global-theme", create_theme("Global"), global_scope=True)
                presets = list_theme_presets(proj)
                names = [p.name for p in presets]
                self.assertIn("local-theme", names)
                self.assertIn("global-theme", names)
            finally:
                themes_mod._global_themes_dir = orig

    def test_list_project_shadows_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)

            global_dir = Path(tmp) / "global_themes"
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                save_theme_preset(None, "shared", create_theme("G"), global_scope=True)
                save_theme_preset(proj, "shared", create_theme("P"))
                presets = list_theme_presets(proj)
                matching = [p for p in presets if p.name == "shared"]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].scope, "project")
            finally:
                themes_mod._global_themes_dir = orig

    def test_list_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: Path(tmp) / "empty_global"
            try:
                self.assertEqual(list_theme_presets(proj), [])
            finally:
                themes_mod._global_themes_dir = orig


class TestDeleteThemePreset(unittest.TestCase):
    def test_delete_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            save_theme_preset(proj, "doomed", create_theme("D"))
            self.assertTrue(delete_theme_preset(proj, "doomed"))
            with self.assertRaises(FileNotFoundError):
                get_theme_preset(proj, "doomed")

    def test_delete_missing_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)
            self.assertFalse(delete_theme_preset(proj, "nonexistent"))


class TestCloneThemePreset(unittest.TestCase):
    def test_clone_to_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)

            save_theme_preset(proj, "local", create_theme("L"))

            global_dir = Path(tmp) / "global_themes"
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                path = clone_theme_preset(proj, "local", to_global=True)
                self.assertTrue(path.exists())
                preset = get_theme_preset(proj, "local", global_scope=True)
                self.assertEqual(preset.scope, "global")
            finally:
                themes_mod._global_themes_dir = orig

    def test_clone_to_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            from pbi.project import Project
            proj = Project.find(pbip)

            global_dir = Path(tmp) / "global_themes"
            import pbi.themes as themes_mod
            orig = themes_mod._global_themes_dir
            themes_mod._global_themes_dir = lambda: global_dir
            try:
                save_theme_preset(None, "shared", create_theme("S"), global_scope=True)
                clone_theme_preset(proj, "shared", to_global=False)
                preset = get_theme_preset(proj, "shared")
                self.assertEqual(preset.scope, "project")
            finally:
                themes_mod._global_themes_dir = orig


class TestDumpThemePreset(unittest.TestCase):
    def test_dump_roundtrip(self) -> None:
        import yaml
        data = create_theme("Test")
        preset = ThemePreset(
            name="test",
            path=Path("/tmp/test.yaml"),
            data=data,
            description="A test theme",
        )
        dumped = dump_theme_preset(preset)
        parsed = yaml.safe_load(dumped)
        self.assertEqual(parsed["name"], "test")
        self.assertEqual(parsed["description"], "A test theme")
        self.assertEqual(parsed["theme"]["foreground"], data["foreground"])


# ── Theme save/load CLI command tests ────────────────────────────────────


class TestThemeSaveCommand(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Active", foreground="#222222")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            # Save
            result = runner.invoke(app, [
                "theme", "save", "my-brand", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("my-brand", result.stdout)

            # Verify preset file exists
            preset_path = Path(tmp) / ".pbi-themes" / "my-brand.yaml"
            self.assertTrue(preset_path.exists())

    def test_save_no_theme_errors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "save", "test", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("No custom theme", result.stdout)


class TestThemeLoadCommand(unittest.TestCase):
    def test_load_applies_preset(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            # Create an initial theme so we can save it
            theme_data = create_theme("Initial", foreground="#111111")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            # Save as preset
            runner.invoke(app, ["theme", "save", "saved-theme", "-p", str(pbip)])

            # Delete the custom theme
            runner.invoke(app, ["theme", "delete", "--force", "-p", str(pbip)])

            # Load from preset
            result = runner.invoke(app, [
                "theme", "load", "saved-theme", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("saved-theme", result.stdout)

            # Verify theme is now applied
            result = runner.invoke(app, ["theme", "get", "foreground", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("#111111", result.stdout)

    def test_load_not_found_errors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "load", "nonexistent", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("not found", result.stdout)


class TestThemePresetListCommand(unittest.TestCase):
    def test_list_shows_presets(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Active")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)

            runner.invoke(app, ["theme", "save", "brand-a", "-p", str(pbip)])
            runner.invoke(app, ["theme", "save", "brand-b", "-p", str(pbip)])

            result = runner.invoke(app, [
                "theme", "preset", "list", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("brand-a", result.stdout)
            self.assertIn("brand-b", result.stdout)

    def test_list_empty(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "preset", "list", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No theme presets", result.stdout)


class TestThemePresetGetCommand(unittest.TestCase):
    def test_get_shows_yaml(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Active", foreground="#333333")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            runner.invoke(app, ["theme", "save", "my-theme", "-p", str(pbip)])

            result = runner.invoke(app, [
                "theme", "preset", "get", "my-theme", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("my-theme", result.stdout)
            self.assertIn("#333333", result.stdout)


class TestThemePresetDeleteCommand(unittest.TestCase):
    def test_delete_with_force(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Active")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            runner.invoke(app, ["theme", "save", "doomed", "-p", str(pbip)])

            result = runner.invoke(app, [
                "theme", "preset", "delete", "doomed", "--force", "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deleted", result.stdout)

            # Verify gone
            result = runner.invoke(app, [
                "theme", "preset", "get", "doomed", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)


class TestThemePresetCloneCommand(unittest.TestCase):
    def test_clone_requires_direction(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, [
                "theme", "preset", "clone", "x", "-p", str(pbip),
            ])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("--to-global", result.stdout)


if __name__ == "__main__":
    unittest.main()
