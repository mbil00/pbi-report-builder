"""Tests for custom visual discovery, schema extraction, and registration."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.custom_visuals import (
    CustomVisualInfo,
    auto_install,
    extract_capabilities,
    install_custom_visual,
    load_custom_schemas,
    scan_custom_visuals,
    _capabilities_to_compact_schema,
    _convert_property_type,
)
from pbi.project import Project
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA, REPORT_SCHEMA
from pbi.visual_schema import (
    clear_custom_schemas,
    get_data_roles,
    get_visual_schema,
    get_visual_types,
    register_custom_schemas,
)

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────


def _make_project(root: Path) -> Project:
    """Scaffold a minimal PBIP project."""
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    pages_dir = definition / "pages"
    pages_dir.mkdir(parents=True)

    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA}) + "\n",
        encoding="utf-8",
    )
    (pages_dir / "pages.json").write_text(
        json.dumps({"$schema": PAGES_METADATA_SCHEMA, "pageOrder": []}) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


def _add_visual(project: Project, page_name: str, visual_name: str, visual_type: str) -> None:
    """Add a minimal visual to a project page."""
    pages_dir = project.definition_folder / "pages"

    # Create page if needed
    page_dir = pages_dir / page_name
    if not page_dir.exists():
        page_dir.mkdir(parents=True)
        (page_dir / "page.json").write_text(
            json.dumps({
                "$schema": PAGE_SCHEMA,
                "name": page_name,
                "displayName": page_name,
                "width": 1280,
                "height": 720,
            }) + "\n",
            encoding="utf-8",
        )
        # Update page order
        meta_path = pages_dir / "pages.json"
        meta = json.loads(meta_path.read_text())
        meta.setdefault("pageOrder", []).append(page_name)
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

    # Create visual
    visual_dir = page_dir / "visuals" / visual_name
    visual_dir.mkdir(parents=True, exist_ok=True)
    visual_data = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json",
        "name": visual_name,
        "position": {"x": 0, "y": 0, "width": 200, "height": 200},
        "visual": {"visualType": visual_type},
    }
    (visual_dir / "visual.json").write_text(
        json.dumps(visual_data) + "\n",
        encoding="utf-8",
    )
    project.clear_caches()


def _make_pbiviz(
    path: Path,
    visual_type: str = "MyCustomChart",
    display_name: str = "My Custom Chart",
    data_roles: list[dict] | None = None,
    objects: dict | None = None,
) -> Path:
    """Create a mock .pbiviz zip archive with capabilities."""
    if data_roles is None:
        data_roles = [
            {"name": "Category", "displayName": "Category", "kind": 0},
            {"name": "Values", "displayName": "Values", "kind": 1},
        ]
    if objects is None:
        objects = {
            "legend": {
                "displayName": "Legend",
                "properties": {
                    "show": {"type": {"bool": True}},
                    "position": {
                        "type": {
                            "enumeration": [
                                {"value": "Top"},
                                {"value": "Bottom"},
                                {"value": "Left"},
                                {"value": "Right"},
                            ]
                        }
                    },
                    "fontSize": {"type": {"numeric": True}},
                    "color": {"type": {"fill": {"solid": {"color": True}}}},
                },
            },
            "dataPoint": {
                "displayName": "Data colors",
                "properties": {
                    "fill": {"type": {"fill": {"solid": {"color": True}}}},
                    "transparency": {"type": {"integer": True}},
                },
            },
        }

    guid = "abc123def456"
    pbiviz_json = {
        "visual": {
            "name": visual_type,
            "displayName": display_name,
            "visualClassName": visual_type,
            "capabilities": {
                "dataRoles": data_roles,
                "objects": objects,
                "dataViewMappings": [{"categorical": {"categories": {"for": {"in": "Category"}}}}],
            },
        },
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"resources/{guid}.pbiviz.json",
            json.dumps(pbiviz_json),
        )
        zf.writestr("package.json", json.dumps({"name": visual_type}))

    path.write_bytes(buf.getvalue())
    return path


# ── Extract capabilities ──────────────────────────────────────────


def test_extract_capabilities_from_pbiviz():
    with tempfile.TemporaryDirectory() as tmp:
        pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")
        caps = extract_capabilities(pbiviz_path)

        assert caps["visual_type"] == "MyCustomChart"
        assert caps["display_name"] == "My Custom Chart"
        assert len(caps["dataRoles"]) == 2
        assert caps["dataRoles"][0]["name"] == "Category"
        assert caps["dataRoles"][1]["kind"] == 1
        assert "legend" in caps["objects"]
        assert "show" in caps["objects"]["legend"]["properties"]


def test_extract_capabilities_missing_file():
    import pytest
    with pytest.raises(FileNotFoundError):
        extract_capabilities(Path("/nonexistent/file.pbiviz"))


def test_extract_capabilities_invalid_zip():
    import pytest
    with tempfile.TemporaryDirectory() as tmp:
        bad_file = Path(tmp) / "bad.pbiviz"
        bad_file.write_text("not a zip")
        with pytest.raises(ValueError, match="Not a valid zip"):
            extract_capabilities(bad_file)


def test_extract_capabilities_no_pbiviz_json():
    import pytest
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "empty.pbiviz"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "nothing here")
        path.write_bytes(buf.getvalue())
        with pytest.raises(ValueError, match="No .pbiviz.json found"):
            extract_capabilities(path)


# ── Compact schema conversion ─────────────────────────────────────


def test_convert_property_type_bool():
    assert _convert_property_type({"type": {"bool": True}}) == "bool"


def test_convert_property_type_numeric():
    assert _convert_property_type({"type": {"numeric": True}}) == "num"


def test_convert_property_type_integer():
    assert _convert_property_type({"type": {"integer": True}}) == "int"


def test_convert_property_type_text():
    assert _convert_property_type({"type": {"text": True}}) == "text"


def test_convert_property_type_color():
    assert _convert_property_type({"type": {"fill": {"solid": {"color": True}}}}) == "color"


def test_convert_property_type_enum():
    result = _convert_property_type({
        "type": {"enumeration": [{"value": "Top"}, {"value": "Bottom"}]}
    })
    assert result == ["Top", "Bottom"]


def test_convert_property_type_formatting():
    assert _convert_property_type({"type": {"formatting": True}}) == "fmt"


def test_convert_property_type_unknown():
    assert _convert_property_type({"type": {"complex": True}}) == "any"


def test_convert_property_type_no_type():
    assert _convert_property_type({}) == "any"


def test_capabilities_to_compact_schema():
    caps = {
        "dataRoles": [
            {"name": "Category", "displayName": "Category", "kind": 0},
            {"name": "Values", "displayName": "Values", "kind": 1},
        ],
        "objects": {
            "legend": {
                "displayName": "Legend",
                "properties": {
                    "show": {"type": {"bool": True}},
                    "position": {"type": {"enumeration": [{"value": "Top"}, {"value": "Bottom"}]}},
                },
            },
        },
    }
    compact = _capabilities_to_compact_schema(caps)

    assert compact["dataRoles"]["Category"] == {"displayName": "Category", "kind": 0}
    assert compact["dataRoles"]["Values"] == {"displayName": "Values", "kind": 1}
    assert compact["objects"]["legend"]["show"] == "bool"
    assert compact["objects"]["legend"]["position"] == ["Top", "Bottom"]


# ── Scan ──────────────────────────────────────────────────────────


def test_scan_no_custom_visuals():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "chart1", "clusteredBarChart")
        results = scan_custom_visuals(proj)
        assert results == []


def test_scan_finds_custom_visual():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "custom1", "MyCustomChart")
        _add_visual(proj, "page1", "custom2", "MyCustomChart")
        _add_visual(proj, "page1", "bar1", "clusteredBarChart")

        results = scan_custom_visuals(proj)
        assert len(results) == 1
        assert results[0].visual_type == "MyCustomChart"
        assert results[0].visual_count == 2
        assert results[0].schema_installed is False


def test_scan_multiple_custom_types():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "cv1", "CustomTypeA")
        _add_visual(proj, "page1", "cv2", "CustomTypeB")

        results = scan_custom_visuals(proj)
        types = {r.visual_type for r in results}
        assert types == {"CustomTypeA", "CustomTypeB"}


def test_scan_detects_installed_schema():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "cv1", "MyCustomChart")

        # Install a schema manually
        schema_dir = proj.root / ".pbi-custom-schemas"
        schema_dir.mkdir()
        (schema_dir / "MyCustomChart.json").write_text(
            json.dumps({"objects": {}, "dataRoles": {}}) + "\n",
            encoding="utf-8",
        )

        results = scan_custom_visuals(proj)
        assert results[0].schema_installed is True


def test_scan_finds_pbiviz_in_custom_visuals_dir():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "cv1", "MyCustomChart")

        cv_dir = proj.report_folder / "CustomVisuals"
        cv_dir.mkdir(parents=True)
        _make_pbiviz(cv_dir / "MyChart.pbiviz")

        results = scan_custom_visuals(proj)
        assert results[0].pbiviz_path is not None


# ── Install ───────────────────────────────────────────────────────


def test_install_creates_schema_file():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")

        result = install_custom_visual(proj, pbiviz_path)

        assert result.visual_type == "MyCustomChart"
        assert result.display_name == "My Custom Chart"
        assert result.role_count == 2
        assert result.object_count == 2
        assert result.property_count > 0

        schema_file = proj.root / ".pbi-custom-schemas" / "MyCustomChart.json"
        assert schema_file.exists()

        schema = json.loads(schema_file.read_text())
        assert "legend" in schema["objects"]
        assert schema["objects"]["legend"]["show"] == "bool"
        assert schema["objects"]["legend"]["position"] == ["Top", "Bottom", "Left", "Right"]
        assert schema["objects"]["legend"]["fontSize"] == "num"
        assert schema["objects"]["legend"]["color"] == "color"
        assert schema["objects"]["dataPoint"]["fill"] == "color"
        assert schema["objects"]["dataPoint"]["transparency"] == "int"
        assert schema["dataRoles"]["Category"]["kind"] == 0
        assert schema["dataRoles"]["Values"]["kind"] == 1


def test_install_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")

        install_custom_visual(proj, pbiviz_path)
        result = install_custom_visual(proj, pbiviz_path)
        assert result.visual_type == "MyCustomChart"


# ── Schema loading ────────────────────────────────────────────────


def test_load_custom_schemas_empty():
    with tempfile.TemporaryDirectory() as tmp:
        schemas = load_custom_schemas(Path(tmp))
        assert schemas == {}


def test_load_custom_schemas_reads_files():
    with tempfile.TemporaryDirectory() as tmp:
        schema_dir = Path(tmp) / ".pbi-custom-schemas"
        schema_dir.mkdir()
        (schema_dir / "MyChart.json").write_text(
            json.dumps({"objects": {"legend": {"show": "bool"}}, "dataRoles": {}})
        )
        schemas = load_custom_schemas(Path(tmp))
        assert "MyChart" in schemas
        assert schemas["MyChart"]["objects"]["legend"]["show"] == "bool"


# ── Schema engine integration ─────────────────────────────────────


def test_register_custom_schemas_makes_type_available():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")
            install_custom_visual(proj, pbiviz_path)

            count = register_custom_schemas(proj.root)
            assert count == 1

            assert "MyCustomChart" in get_visual_types()
            schema = get_visual_schema("MyCustomChart")
            assert schema is not None
            assert "legend" in schema["objects"]

            roles = get_data_roles("MyCustomChart")
            assert roles is not None
            assert "Category" in roles
            assert roles["Category"]["kind"] == 0
    finally:
        clear_custom_schemas()


def test_builtin_types_still_work_after_custom_registration():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")
            install_custom_visual(proj, pbiviz_path)
            register_custom_schemas(proj.root)

            assert get_visual_schema("clusteredBarChart") is not None
            assert "clusteredBarChart" in get_visual_types()
    finally:
        clear_custom_schemas()


# ── CLI commands ──────────────────────────────────────────────────


def test_cli_scan_no_custom():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "bar1", "clusteredBarChart")

        result = runner.invoke(app, ["visual", "plugin", "scan", "-p", str(proj.root)])
        assert result.exit_code == 0
        assert "No custom visuals" in result.output


def test_cli_scan_finds_custom():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "cv1", "MyCustomChart")

        result = runner.invoke(app, ["visual", "plugin", "scan", "-p", str(proj.root)])
        assert result.exit_code == 0
        assert "MyCustomChart" in result.output


def test_cli_scan_json():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        _add_visual(proj, "page1", "cv1", "MyCustomChart")

        result = runner.invoke(app, ["visual", "plugin", "scan", "--json", "-p", str(proj.root)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["visualType"] == "MyCustomChart"
        assert data[0]["count"] == 1


def test_cli_install_from_file():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")

            result = runner.invoke(app, [
                "visual", "plugin", "install", str(pbiviz_path), "-p", str(proj.root),
            ])
            assert result.exit_code == 0
            assert "MyCustomChart" in result.output
            assert "2 roles" in result.output

            schema_file = proj.root / ".pbi-custom-schemas" / "MyCustomChart.json"
            assert schema_file.exists()
    finally:
        clear_custom_schemas()


def test_cli_install_auto_finds_pbiviz():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))

            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            result = runner.invoke(app, [
                "visual", "plugin", "install", "-p", str(proj.root),
            ])
            assert result.exit_code == 0
            assert "MyCustomChart" in result.output
    finally:
        clear_custom_schemas()


def test_cli_install_no_pbiviz_found():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))

        result = runner.invoke(app, [
            "visual", "plugin", "install", "-p", str(proj.root),
        ])
        assert result.exit_code == 0
        assert "No .pbiviz files" in result.output


def test_cli_list_empty():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))

        result = runner.invoke(app, [
            "visual", "plugin", "list", "-p", str(proj.root),
        ])
        assert result.exit_code == 0
        assert "No custom visual schemas" in result.output


def test_cli_list_installed():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")
            install_custom_visual(proj, pbiviz_path)

            result = runner.invoke(app, [
                "visual", "plugin", "list", "-p", str(proj.root),
            ])
            assert result.exit_code == 0
            assert "MyCustomChart" in result.output
    finally:
        clear_custom_schemas()


def test_cli_remove():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            pbiviz_path = _make_pbiviz(Path(tmp) / "MyChart.pbiviz")
            install_custom_visual(proj, pbiviz_path)

            schema_file = proj.root / ".pbi-custom-schemas" / "MyCustomChart.json"
            assert schema_file.exists()

            result = runner.invoke(app, [
                "visual", "plugin", "remove", "MyCustomChart", "--force", "-p", str(proj.root),
            ])
            assert result.exit_code == 0
            assert "Removed" in result.output
            assert not schema_file.exists()
    finally:
        clear_custom_schemas()


def test_cli_remove_nonexistent():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))

        result = runner.invoke(app, [
            "visual", "plugin", "remove", "NonExistent", "--force", "-p", str(proj.root),
        ])
        assert result.exit_code == 1
        assert "No schema installed" in result.output


# ── End-to-end: scan → install → validate ─────────────────────────


def test_end_to_end_scan_install_validates():
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            _add_visual(proj, "page1", "cv1", "MyCustomChart")

            # Scan shows custom visual
            scan_results = scan_custom_visuals(proj)
            assert len(scan_results) == 1
            assert scan_results[0].schema_installed is False

            # Place pbiviz and install
            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            # Scan now finds the pbiviz
            proj.clear_caches()
            scan_results = scan_custom_visuals(proj)
            assert scan_results[0].pbiviz_path is not None

            # Install
            from pbi.custom_visuals import install_all_from_project
            installed = install_all_from_project(proj)
            assert len(installed) == 1

            # After install, scan shows schema installed
            proj.clear_caches()
            scan_results = scan_custom_visuals(proj)
            assert scan_results[0].schema_installed is True

            # Schema engine now knows the type
            register_custom_schemas(proj.root)
            assert get_visual_schema("MyCustomChart") is not None

            # Roles are available
            roles = get_data_roles("MyCustomChart")
            assert "Category" in roles
            assert "Values" in roles
    finally:
        clear_custom_schemas()


# ── Auto-install ──────────────────────────────────────────────────


def test_auto_install_installs_new_pbiviz():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        cv_dir = proj.report_folder / "CustomVisuals"
        cv_dir.mkdir(parents=True)
        _make_pbiviz(cv_dir / "MyChart.pbiviz")

        results = auto_install(proj)
        assert len(results) == 1
        assert results[0].visual_type == "MyCustomChart"

        schema_file = proj.root / ".pbi-custom-schemas" / "MyCustomChart.json"
        assert schema_file.exists()


def test_auto_install_skips_already_installed():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        cv_dir = proj.report_folder / "CustomVisuals"
        cv_dir.mkdir(parents=True)
        _make_pbiviz(cv_dir / "MyChart.pbiviz")

        # First run installs
        results = auto_install(proj)
        assert len(results) == 1

        # Second run skips (already installed)
        results = auto_install(proj)
        assert len(results) == 0


def test_auto_install_no_pbiviz_files():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        results = auto_install(proj)
        assert results == []


def test_auto_install_multiple_pbiviz():
    with tempfile.TemporaryDirectory() as tmp:
        proj = _make_project(Path(tmp))
        cv_dir = proj.report_folder / "CustomVisuals"
        cv_dir.mkdir(parents=True)
        _make_pbiviz(cv_dir / "ChartA.pbiviz", visual_type="ChartA", display_name="Chart A")
        _make_pbiviz(cv_dir / "ChartB.pbiviz", visual_type="ChartB", display_name="Chart B")

        results = auto_install(proj)
        types = {r.visual_type for r in results}
        assert types == {"ChartA", "ChartB"}


def test_auto_install_on_project_load():
    """Verify that get_project() auto-installs custom visual schemas."""
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            # Simulate what get_project() does
            newly_installed = auto_install(proj)
            assert len(newly_installed) == 1

            count = register_custom_schemas(proj.root)
            assert count == 1
            assert get_visual_schema("MyCustomChart") is not None
    finally:
        clear_custom_schemas()


def test_cli_auto_installs_on_any_command():
    """Any CLI command touching the project triggers auto-install."""
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            _add_visual(proj, "page1", "cv1", "MyCustomChart")

            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            # Running any command should auto-install
            result = runner.invoke(app, ["visual", "plugin", "scan", "-p", str(proj.root)])
            assert result.exit_code == 0
            assert "Auto-installed" in result.output
            assert "MyCustomChart" in result.output

            # Schema file should exist now
            schema_file = proj.root / ".pbi-custom-schemas" / "MyCustomChart.json"
            assert schema_file.exists()

            # Running again should NOT auto-install (already done)
            result = runner.invoke(app, ["visual", "plugin", "scan", "-p", str(proj.root)])
            assert "Auto-installed" not in result.output
    finally:
        clear_custom_schemas()
