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
    _build_theme_defaults,
    _cascade_visual_styles_colors,
    _ensure_resource_entry,
    _fix_theme_resource_path,
    _load_theme_preset,
    _lookup_theme_default,
    _normalize_resource_item,
    _validate_hex_color,
    audit_theme_overrides,
    clone_theme_preset,
    create_theme,
    decode_theme_style_value,
    delete_theme_preset,
    delete_visual_style,
    dump_theme_preset,
    encode_theme_style_value,
    fix_theme_overrides,
    get_theme_preset,
    get_theme_property,
    get_visual_style_entries,
    list_visual_style_roles,
    list_theme_presets,
    list_visual_style_types,
    parse_style_assignment,
    save_theme_preset,
    set_theme_property,
    set_visual_style_property,
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
                "items": [{"type": "CustomTheme", "name": f"{theme_name}.json", "path": f"{theme_name}.json"}],
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


# ── Visual style unit tests ─────────────────────────────────────────────


class TestParseStyleAssignment(unittest.TestCase):
    def test_simple(self) -> None:
        obj, prop, sel, val = parse_style_assignment("legend.show=true")
        self.assertEqual(obj, "legend")
        self.assertEqual(prop, "show")
        self.assertIsNone(sel)
        self.assertEqual(val, "true")

    def test_with_selector(self) -> None:
        obj, prop, sel, val = parse_style_assignment("filterCard.border[Applied]=true")
        self.assertEqual(obj, "filterCard")
        self.assertEqual(prop, "border")
        self.assertEqual(sel, "Applied")
        self.assertEqual(val, "true")

    def test_invalid_no_equals(self) -> None:
        with self.assertRaises(ValueError):
            parse_style_assignment("legend.show")

    def test_invalid_no_dot(self) -> None:
        with self.assertRaises(ValueError):
            parse_style_assignment("legend=true")


class TestEncodeThemeStyleValue(unittest.TestCase):
    def test_color_hex(self) -> None:
        result = encode_theme_style_value("#FF0000", "color")
        self.assertEqual(result, {"solid": {"color": "#FF0000"}})

    def test_color_token(self) -> None:
        result = encode_theme_style_value("foreground", "color")
        self.assertEqual(result, {"solid": {"color": "foreground"}})

    def test_bool(self) -> None:
        self.assertTrue(encode_theme_style_value("true", "bool"))
        self.assertFalse(encode_theme_style_value("false", "bool"))

    def test_int(self) -> None:
        self.assertEqual(encode_theme_style_value("42", "int"), 42)

    def test_num_float(self) -> None:
        self.assertEqual(encode_theme_style_value("0.5", "num"), 0.5)

    def test_enum(self) -> None:
        result = encode_theme_style_value("dotted", ["solid", "dotted", "dashed"])
        self.assertEqual(result, "dotted")

    def test_fallback_bool(self) -> None:
        self.assertTrue(encode_theme_style_value("true", None))

    def test_fallback_int(self) -> None:
        self.assertEqual(encode_theme_style_value("3", None), 3)

    def test_fallback_string(self) -> None:
        self.assertEqual(encode_theme_style_value("hello", None), "hello")

    def test_palette_token_auto(self) -> None:
        result = encode_theme_style_value("backgroundLight", None)
        self.assertEqual(result, {"solid": {"color": "backgroundLight"}})


class TestDecodeThemeStyleValue(unittest.TestCase):
    def test_color_object(self) -> None:
        self.assertEqual(decode_theme_style_value({"solid": {"color": "#FFF"}}), "#FFF")

    def test_scalar(self) -> None:
        self.assertEqual(decode_theme_style_value(True), True)
        self.assertEqual(decode_theme_style_value(3), 3)

    def test_recursive_nested_object(self) -> None:
        raw = {
            "expr": {"ThemeDataColor": {"ColorId": 3}},
            "fallback": {"solid": {"color": "#ABCDEF"}},
        }
        self.assertEqual(
            decode_theme_style_value(raw),
            {
                "expr": {"ThemeDataColor": {"ColorId": 3}},
                "fallback": "#ABCDEF",
            },
        )


class TestSetVisualStyleProperty(unittest.TestCase):
    def test_set_creates_structure(self) -> None:
        data: dict = {"name": "test"}
        set_visual_style_property(data, "*", "legend", "show", "true")
        entries = get_visual_style_entries(data, "*")
        self.assertIsNotNone(entries)
        self.assertIn("legend", entries)
        self.assertEqual(entries["legend"][0]["show"], True)

    def test_set_with_selector(self) -> None:
        data: dict = {"name": "test"}
        set_visual_style_property(data, "*", "filterCard", "border", "true", selector="Applied")
        entries = get_visual_style_entries(data, "*")
        found = [e for e in entries["filterCard"] if e.get("$id") == "Applied"]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["border"])

    def test_set_color_encodes_correctly(self) -> None:
        data: dict = {"name": "test"}
        set_visual_style_property(data, "*", "background", "backgroundColor", "#ffffff")
        entries = get_visual_style_entries(data, "*")
        self.assertEqual(
            entries["background"][0]["backgroundColor"],
            {"solid": {"color": "#FFFFFF"}},
        )

    def test_set_json_value_preserves_nested_shape(self) -> None:
        data: dict = {"name": "test"}
        set_visual_style_property(
            data,
            "*",
            "dataPoint",
            "fillRule",
            '{"inputRole":"Measure","output":{"property":"fill","selector":["Category"]}}',
        )
        entries = get_visual_style_entries(data, "*")
        self.assertEqual(
            entries["dataPoint"][0]["fillRule"],
            {
                "inputRole": "Measure",
                "output": {"property": "fill", "selector": ["Category"]},
            },
        )

    def test_set_with_role_branch(self) -> None:
        data: dict = {"name": "test"}
        set_visual_style_property(data, "columnChart", "legend", "show", "true", role="Series")
        self.assertEqual(list_visual_style_roles(data, "columnChart"), ["Series"])
        entries = get_visual_style_entries(data, "columnChart", role="Series")
        self.assertTrue(entries["legend"][0]["show"])


class TestDeleteVisualStyle(unittest.TestCase):
    def test_delete_type(self) -> None:
        data: dict = {
            "visualStyles": {
                "columnChart": {"*": {"legend": [{"show": True}]}},
                "pieChart": {"*": {"labels": [{"show": True}]}},
            }
        }
        self.assertTrue(delete_visual_style(data, "columnChart"))
        self.assertNotIn("columnChart", data["visualStyles"])
        self.assertIn("pieChart", data["visualStyles"])

    def test_delete_object(self) -> None:
        data: dict = {
            "visualStyles": {
                "columnChart": {"*": {"legend": [{"show": True}], "labels": [{"show": True}]}},
            }
        }
        self.assertTrue(delete_visual_style(data, "columnChart", "legend"))
        entries = get_visual_style_entries(data, "columnChart")
        self.assertNotIn("legend", entries)
        self.assertIn("labels", entries)

    def test_delete_missing(self) -> None:
        data: dict = {"visualStyles": {}}
        self.assertFalse(delete_visual_style(data, "nonexistent"))

    def test_delete_cleans_empty_parents(self) -> None:
        data: dict = {
            "visualStyles": {
                "columnChart": {"*": {"legend": [{"show": True}]}},
            }
        }
        delete_visual_style(data, "columnChart", "legend")
        self.assertNotIn("columnChart", data["visualStyles"])

    def test_delete_specific_role_only(self) -> None:
        data: dict = {
            "visualStyles": {
                "columnChart": {
                    "*": {"legend": [{"show": True}]},
                    "Series": {"legend": [{"show": False}]},
                },
            }
        }
        self.assertTrue(delete_visual_style(data, "columnChart", role="Series"))
        self.assertIn("*", data["visualStyles"]["columnChart"])
        self.assertNotIn("Series", data["visualStyles"]["columnChart"])


class TestListVisualStyleTypes(unittest.TestCase):
    def test_list(self) -> None:
        data: dict = {
            "visualStyles": {
                "columnChart": {"*": {}},
                "*": {"*": {}},
                "pieChart": {"*": {}},
            }
        }
        types = list_visual_style_types(data)
        self.assertEqual(types, ["*", "columnChart", "pieChart"])

    def test_empty(self) -> None:
        self.assertEqual(list_visual_style_types({}), [])


# ── Visual style CLI tests ──────────────────────────────────────────────


def _scaffold_with_visual_styles(root: Path) -> Path:
    """Create a project with a custom theme that has visualStyles."""
    theme_data = create_theme("Styled")
    theme_data["visualStyles"] = {
        "*": {"*": {
            "background": [{"show": True, "transparency": 0}],
            "categoryAxis": [{"showAxisTitle": True, "gridlineStyle": "dotted"}],
        }},
        "columnChart": {"*": {
            "legend": [{"show": True, "position": "RightCenter"}],
        }},
    }
    return _scaffold_project(root, theme_data=theme_data)


class TestThemeStyleListCommand(unittest.TestCase):
    def test_list(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, ["theme", "style", "list", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("columnChart", result.stdout)

    def test_list_no_styles(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Plain")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, ["theme", "style", "list", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("No visual style", result.stdout)

    def test_list_json_includes_roles(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            theme_data["visualStyles"] = {
                "columnChart": {
                    "*": {"legend": [{"show": True}]},
                    "Series": {"legend": [{"show": False}]},
                }
            }
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, ["theme", "style", "list", "--json", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed[0]["roles"], ["*", "Series"])


class TestThemeStyleGetCommand(unittest.TestCase):
    def test_get_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, ["theme", "style", "get", "columnChart", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("legend", result.stdout)
            self.assertIn("RightCenter", result.stdout)

    def test_get_object(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, ["theme", "style", "get", "*", "categoryAxis", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("showAxisTitle", result.stdout)
            self.assertIn("dotted", result.stdout)

    def test_get_raw(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, ["theme", "style", "get", "--raw", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            parsed = json.loads(result.stdout)
            self.assertIn("columnChart", parsed)

    def test_get_role_branch(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            theme_data["visualStyles"] = {
                "columnChart": {
                    "*": {"legend": [{"show": True}]},
                    "Series": {"legend": [{"show": False}]},
                }
            }
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(
                app,
                ["theme", "style", "get", "columnChart", "--role", "Series", "-p", str(pbip)],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Series", result.stdout)
            self.assertIn("False", result.stdout)


class TestThemeStyleSetCommand(unittest.TestCase):
    def test_set_new_property(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, [
                "theme", "style", "set", "columnChart",
                "legend.show=true", "legend.position=RightCenter",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify
            result = runner.invoke(app, ["theme", "style", "get", "columnChart", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("RightCenter", result.stdout)

    def test_set_wildcard_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, [
                "theme", "style", "set", "*",
                "background.show=true",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)

    def test_set_with_selector(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(app, [
                "theme", "style", "set", "*",
                "filterCard.border[Applied]=true",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)

    def test_set_json_value_in_role_branch(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(
                app,
                [
                    "theme",
                    "style",
                    "set",
                    "columnChart",
                    'legend.complex={"expr":{"ThemeDataColor":{"ColorId":2}}}',
                    "--role",
                    "Series",
                    "-p",
                    str(pbip),
                ],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            raw = runner.invoke(
                app,
                ["theme", "style", "get", "columnChart", "--role", "Series", "--raw", "-p", str(pbip)],
            )
            self.assertEqual(raw.exit_code, 0, raw.stdout)
            parsed = json.loads(raw.stdout)
            self.assertEqual(parsed["legend"][0]["complex"]["expr"]["ThemeDataColor"]["ColorId"], 2)


class TestThemeStyleDeleteCommand(unittest.TestCase):
    def test_delete_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, [
                "theme", "style", "delete", "columnChart", "--force",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deleted", result.stdout)

            # Verify gone
            result = runner.invoke(app, ["theme", "style", "get", "columnChart", "-p", str(pbip)])
            self.assertIn("No style overrides", result.stdout)

    def test_delete_object(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, [
                "theme", "style", "delete", "*", "categoryAxis", "--force",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deleted", result.stdout)

    def test_delete_missing(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, [
                "theme", "style", "delete", "nonexistent", "--force",
                "-p", str(pbip),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No visual style", result.stdout)

    def test_delete_role_branch_only(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            theme_data = create_theme("Test")
            theme_data["visualStyles"] = {
                "columnChart": {
                    "*": {"legend": [{"show": True}]},
                    "Series": {"legend": [{"show": False}]},
                }
            }
            pbip = _scaffold_project(Path(tmp), theme_data=theme_data)
            result = runner.invoke(
                app,
                ["theme", "style", "delete", "columnChart", "--role", "Series", "--force", "-p", str(pbip)],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            raw = runner.invoke(
                app,
                ["theme", "style", "get", "columnChart", "--raw", "-p", str(pbip)],
            )
            self.assertEqual(raw.exit_code, 0, raw.stdout)
            parsed = json.loads(raw.stdout)
            self.assertIn("*", parsed)
            self.assertNotIn("Series", parsed)


# ── Theme audit (IMP-09) ──────────────────────────────────────────────


def _scaffold_audit_project(root: Path) -> Path:
    """Create a project with a theme + visuals that have per-visual overrides."""
    from pbi.project import Project

    theme_data = create_theme("AuditTheme")
    theme_data["visualStyles"] = {
        "*": {"*": {
            "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}}],
            "border": [{"color": {"solid": {"color": "#E0DEDE"}}, "show": True}],
        }},
        "tableEx": {"*": {
            "columnHeaders": [{"backColor": {"solid": {"color": "#002C77"}}}],
        }},
    }

    pbip = _scaffold_project(root, theme_data=theme_data)
    proj = Project.find(pbip)
    page = proj.create_page("Dashboard")

    # Visual 1: redundant override (matches theme)
    v1 = proj.create_visual(page, "card")
    v1.data["visual"]["visualContainerObjects"] = {
        "background": [{
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#FFFFFF'"}}}}},
            },
        }],
    }
    v1.save()

    # Visual 2: conflicting override (differs from theme)
    v2 = proj.create_visual(page, "tableEx")
    v2.data["visual"]["visualContainerObjects"] = {
        "border": [{
            "properties": {
                "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#CCCCCC'"}}}}},
            },
        }],
    }
    v2.data["visual"]["objects"] = {
        "columnHeaders": [{
            "properties": {
                "backColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#002C77'"}}}}},
            },
        }],
    }
    v2.save()

    # Visual 3: no overrides (clean)
    proj.create_visual(page, "slicer")

    return pbip


class TestBuildThemeDefaults(unittest.TestCase):
    def test_builds_lookup(self) -> None:
        data = {
            "visualStyles": {
                "*": {"*": {
                    "background": [{"show": True, "color": {"solid": {"color": "#FFF"}}}],
                }},
                "tableEx": {"*": {
                    "columnHeaders": [{"backColor": {"solid": {"color": "#002C77"}}}],
                }},
            },
        }
        defaults = _build_theme_defaults(data)
        self.assertEqual(defaults[("*", "background", "show")], True)
        self.assertEqual(defaults[("*", "background", "color")], "#FFF")
        self.assertEqual(defaults[("tableEx", "columnHeaders", "backColor")], "#002C77")

    def test_type_specific_overrides_wildcard(self) -> None:
        defaults = {
            ("*", "background", "color"): "#FFF",
            ("tableEx", "background", "color"): "#000",
        }
        val, found = _lookup_theme_default(defaults, "tableEx", "background", "color")
        self.assertTrue(found)
        self.assertEqual(val, "#000")

    def test_wildcard_fallback(self) -> None:
        defaults = {("*", "background", "color"): "#FFF"}
        val, found = _lookup_theme_default(defaults, "card", "background", "color")
        self.assertTrue(found)
        self.assertEqual(val, "#FFF")

    def test_not_found(self) -> None:
        defaults = {("*", "background", "color"): "#FFF"}
        val, found = _lookup_theme_default(defaults, "card", "legend", "show")
        self.assertFalse(found)


class TestAuditThemeOverrides(unittest.TestCase):
    def test_finds_redundant_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pbi.project import Project

            pbip = _scaffold_audit_project(Path(tmp))
            proj = Project.find(pbip)
            result = audit_theme_overrides(proj)

            self.assertEqual(result.total_visuals, 3)
            self.assertEqual(result.visuals_with_overrides, 2)

            redundant = [o for o in result.overrides if o.is_match]
            conflicts = [o for o in result.overrides if not o.is_match]

            # card1: background.show=true and background.color=#FFFFFF are redundant
            self.assertTrue(len(redundant) >= 2)
            # table1: border.color=#CCCCCC conflicts with theme #E0DEDE
            conflict_props = [(o.object_name, o.property_name) for o in conflicts]
            self.assertIn(("border", "color"), conflict_props)

    def test_fix_removes_redundant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pbi.project import Project

            pbip = _scaffold_audit_project(Path(tmp))
            proj = Project.find(pbip)
            result = audit_theme_overrides(proj)
            redundant_before = result.redundant_count
            self.assertGreater(redundant_before, 0)

            removed = fix_theme_overrides(proj, result)
            self.assertEqual(removed, redundant_before)

            # Re-audit: no more redundant overrides
            result2 = audit_theme_overrides(proj)
            self.assertEqual(result2.redundant_count, 0)
            # Conflicts should still exist
            self.assertGreater(result2.conflict_count, 0)


class TestThemeAuditCommand(unittest.TestCase):
    def test_audit_output(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_audit_project(Path(tmp))
            result = runner.invoke(app, ["theme", "audit", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("override theme defaults", result.stdout)
            self.assertIn("redundant", result.stdout)

    def test_audit_json(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_audit_project(Path(tmp))
            result = runner.invoke(app, ["theme", "audit", "--json", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            import json as json_mod
            rows = json_mod.loads(result.stdout)
            self.assertIsInstance(rows, list)
            self.assertTrue(len(rows) > 0)
            self.assertIn("redundant", rows[0])

    def test_audit_fix(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_audit_project(Path(tmp))
            result = runner.invoke(app, ["theme", "audit", "--fix", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Removed", result.stdout)

    def test_audit_dry_run(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_audit_project(Path(tmp))
            result = runner.invoke(app, ["theme", "audit", "--dry-run", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Would remove", result.stdout)

    def test_audit_no_theme(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            # Project without custom theme
            pbip = _scaffold_project(Path(tmp))
            result = runner.invoke(app, ["theme", "audit", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 1)


# ── Theme YAML diff integration ───────────────────────────────────────


class TestThemeDiffCommand(unittest.TestCase):
    def test_diff_reports_theme_section_changes(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_project(Path(tmp), theme_data=create_theme("Test"))
            diff_spec = {
                "version": 1,
                "pages": [],
                "theme": {
                    "visualStyles": {
                        "columnChart": {
                            "Series": {
                                "legend": [
                                    {"show": False},
                                ]
                            }
                        }
                    }
                },
            }
            diff_file = Path(tmp) / "theme-diff.yaml"
            diff_file.write_text(json.dumps(diff_spec), encoding="utf-8")

            result = runner.invoke(app, ["diff", str(diff_file), "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Theme", result.stdout)
            self.assertIn("theme.visualStyles.columnChart.Series.legend[0].show", result.stdout)


# ── BUG-031: Resource path must preserve .json extension ──────────────


class TestNormalizeResourceItemPreservesPath(unittest.TestCase):
    """BUG-031: Ensure CustomTheme items have full filename in both name and path."""

    def test_normalizes_name_and_path(self) -> None:
        item = {"name": "MyTheme", "path": "MyTheme.json", "type": "CustomTheme"}
        result = _normalize_resource_item(item)
        self.assertEqual(result["name"], "MyTheme.json")
        self.assertEqual(result["path"], "MyTheme.json")

    def test_adds_json_extension_when_missing(self) -> None:
        item = {"name": "MyTheme", "path": "MyTheme", "type": 202}
        result = _normalize_resource_item(item)
        self.assertEqual(result["name"], "MyTheme.json")
        self.assertEqual(result["path"], "MyTheme.json")

    def test_adds_path_when_absent(self) -> None:
        item = {"name": "MyTheme", "type": 202}
        result = _normalize_resource_item(item)
        self.assertEqual(result["name"], "MyTheme.json")
        self.assertEqual(result["path"], "MyTheme.json")

    def test_already_correct(self) -> None:
        item = {"name": "MyTheme.json", "path": "MyTheme.json", "type": "CustomTheme"}
        result = _normalize_resource_item(item)
        self.assertEqual(result["name"], "MyTheme.json")
        self.assertEqual(result["path"], "MyTheme.json")


class TestEnsureResourceEntryFixesPath(unittest.TestCase):
    """BUG-031: _ensure_resource_entry should fix both name and path."""

    def test_fixes_stem_only_name_and_path(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"type": "CustomTheme", "name": "MyTheme", "path": "MyTheme"}],
            }],
        }
        _ensure_resource_entry(report, "MyTheme")
        item = report["resourcePackages"][0]["items"][0]
        self.assertEqual(item["name"], "MyTheme.json")
        self.assertEqual(item["path"], "MyTheme.json")

    def test_no_duplicate_when_correct(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"type": "CustomTheme", "name": "MyTheme.json", "path": "MyTheme.json"}],
            }],
        }
        _ensure_resource_entry(report, "MyTheme")
        self.assertEqual(len(report["resourcePackages"][0]["items"]), 1)

    def test_creates_with_full_filename(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [],
            }],
        }
        _ensure_resource_entry(report, "MyTheme")
        item = report["resourcePackages"][0]["items"][0]
        self.assertEqual(item["name"], "MyTheme.json")
        self.assertEqual(item["path"], "MyTheme.json")


class TestFixThemeResourcePath(unittest.TestCase):
    """BUG-031: _fix_theme_resource_path repairs name and path in both formats."""

    def test_fixes_flat_format(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"name": "MyTheme", "path": "MyTheme", "type": "CustomTheme"}],
            }],
        }
        self.assertTrue(_fix_theme_resource_path(report, "MyTheme"))
        item = report["resourcePackages"][0]["items"][0]
        self.assertEqual(item["name"], "MyTheme.json")
        self.assertEqual(item["path"], "MyTheme.json")

    def test_fixes_wrapped_format(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "resourcePackage": {
                    "name": "RegisteredResources",
                    "type": 1,
                    "items": [{"name": "MyTheme", "path": "MyTheme", "type": 202}],
                }
            }],
        }
        self.assertTrue(_fix_theme_resource_path(report, "MyTheme"))
        item = report["resourcePackages"][0]["resourcePackage"]["items"][0]
        self.assertEqual(item["name"], "MyTheme.json")
        self.assertEqual(item["path"], "MyTheme.json")

    def test_no_change_when_correct(self) -> None:
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"name": "MyTheme.json", "path": "MyTheme.json", "type": "CustomTheme"}],
            }],
        }
        self.assertFalse(_fix_theme_resource_path(report, "MyTheme"))

    def test_fixes_name_only(self) -> None:
        """Path is correct but name is missing .json."""
        report: dict = {
            "resourcePackages": [{
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"name": "MyTheme", "path": "MyTheme.json", "type": "CustomTheme"}],
            }],
        }
        self.assertTrue(_fix_theme_resource_path(report, "MyTheme"))
        item = report["resourcePackages"][0]["items"][0]
        self.assertEqual(item["name"], "MyTheme.json")


class TestSaveThemeDataRepairsPath(unittest.TestCase):
    """BUG-031: save_theme_data should repair broken resource name/path in report.json."""

    def test_repairs_broken_name_and_path_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from pbi.project import Project
            from pbi.themes import get_theme_data, save_theme_data

            root = Path(tmp)
            theme_data = create_theme("TestTheme")
            pbip = _scaffold_project(root, theme_data=theme_data)

            # Corrupt both name and path in report.json
            report_path = root / "Test.Report" / "definition" / "report.json"
            report = json.loads(report_path.read_text())
            report["resourcePackages"][0]["items"][0]["name"] = "TestTheme"
            report["resourcePackages"][0]["items"][0]["path"] = "TestTheme"
            report_path.write_text(json.dumps(report, indent=2) + "\n")

            # Run save_theme_data (as theme style set / theme set would)
            proj = Project.find(pbip)
            data = get_theme_data(proj)
            save_theme_data(proj, data)

            # Verify both name and path were repaired
            after = json.loads(report_path.read_text())
            item = after["resourcePackages"][0]["items"][0]
            self.assertEqual(item["name"], "TestTheme.json")
            self.assertEqual(item["path"], "TestTheme.json")


# ── BUG-032: fontFamily must not be parsed as int ─────────────────────


class TestEncodeThemeStyleValueStringFallback(unittest.TestCase):
    """BUG-032: fmt/int/num schema types must handle string values gracefully."""

    def test_fmt_string_value(self) -> None:
        result = encode_theme_style_value("Segoe UI Semibold", "fmt")
        self.assertEqual(result, "Segoe UI Semibold")

    def test_int_string_value(self) -> None:
        result = encode_theme_style_value("Segoe UI", "int")
        self.assertEqual(result, "Segoe UI")

    def test_num_string_value(self) -> None:
        result = encode_theme_style_value("Arial", "num")
        self.assertEqual(result, "Arial")

    def test_fmt_numeric_still_works(self) -> None:
        self.assertEqual(encode_theme_style_value("9", "fmt"), 9)
        self.assertEqual(encode_theme_style_value("9.5", "fmt"), 9.5)


# ── BUG-033: Color cascade must update visualStyles ───────────────────


class TestCascadeVisualStylesColors(unittest.TestCase):
    """BUG-033: Theme color changes must cascade to visualStyles."""

    def test_cascade_replaces_colors(self) -> None:
        data = {
            "visualStyles": {
                "tableEx": {"*": {
                    "columnHeaders": [{"backColor": {"solid": {"color": "#5C564E"}}}],
                }},
            },
        }
        count = _cascade_visual_styles_colors(data, {"#5C564E": "#747474"})
        self.assertEqual(count, 1)
        val = data["visualStyles"]["tableEx"]["*"]["columnHeaders"][0]["backColor"]
        self.assertEqual(val, {"solid": {"color": "#747474"}})

    def test_cascade_case_insensitive(self) -> None:
        data = {
            "visualStyles": {
                "*": {"*": {
                    "border": [{"color": {"solid": {"color": "#edebe9"}}}],
                }},
            },
        }
        count = _cascade_visual_styles_colors(data, {"#EDEBE9": "#E0DEDE"})
        self.assertEqual(count, 1)
        self.assertEqual(
            data["visualStyles"]["*"]["*"]["border"][0]["color"]["solid"]["color"],
            "#E0DEDE",
        )

    def test_no_match_returns_zero(self) -> None:
        data = {
            "visualStyles": {
                "*": {"*": {"border": [{"show": True}]}},
            },
        }
        self.assertEqual(_cascade_visual_styles_colors(data, {"#FF0000": "#00FF00"}), 0)


class TestSetThemePropertyCascadesToVisualStyles(unittest.TestCase):
    """BUG-033: set_theme_property should cascade color changes to visualStyles."""

    def test_cascade_updates_visual_styles(self) -> None:
        data = {
            "foreground": "#333333",
            "visualStyles": {
                "*": {"*": {
                    "title": [{"fontColor": {"solid": {"color": "#333333"}}}],
                }},
            },
        }
        changed = set_theme_property(data, "foreground", "#111111")
        self.assertIn("foreground", changed)
        # Should have cascaded to visualStyles
        val = data["visualStyles"]["*"]["*"]["title"][0]["fontColor"]
        self.assertEqual(val, {"solid": {"color": "#111111"}})


# ── BUG-034: theme get shows visualStyles ─────────────────────────────


class TestThemeGetShowsVisualStyles(unittest.TestCase):
    """BUG-034: theme get should display visualStyles properties."""

    def test_overview_includes_visual_styles(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = _scaffold_with_visual_styles(Path(tmp))
            result = runner.invoke(app, ["theme", "get", "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Visual Styles", result.stdout)
            self.assertIn("categoryAxis", result.stdout)
            self.assertIn("showAxisTitle", result.stdout)


if __name__ == "__main__":
    unittest.main()
