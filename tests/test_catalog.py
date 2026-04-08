from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from pbi.catalog import get_catalog_item, list_catalog_items, validate_catalog
from pbi.cli import app
from pbi.components import apply_component, list_components, save_component_from_yaml
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from pbi.project import Project
from pbi.validate import validate_project
from pbi.visual_schema import get_data_roles
from pbi.styles import create_style
from pbi.templates import save_template
from pbi.visual_templates import (
    apply_visual_template,
    list_visual_templates,
    register_visual_template,
)
from tests.cli_regressions_support import make_project


class CatalogTests(unittest.TestCase):
    def test_list_catalog_items_includes_bundled_visual_templates(self) -> None:
        items = list_catalog_items(None, kind="visual")
        refs = {(item.kind, item.name, item.scope) for item in items}
        self.assertIn(("visual", "hero-kpi-card", "bundled"), refs)

    def test_list_catalog_items_aggregates_existing_asset_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            project.create_visual(page, "cardVisual")

            create_style(project, "card-style", {"border.show": True})
            save_template(project, page, "sales-page")

            component_yaml = root / "component.yaml"
            component_yaml.write_text(
                "\n".join(
                    [
                        "visuals:",
                        "- type: cardVisual",
                        "  name: tile",
                        "  position: 0, 0",
                        "  size: 260 x 120",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            save_component_from_yaml(project, component_yaml, "kpi-tile")

            items = list_catalog_items(project)
            refs = {(item.kind, item.name) for item in items}

            self.assertIn(("style", "card-style"), refs)
            self.assertIn(("page", "sales-page"), refs)
            self.assertIn(("component", "kpi-tile"), refs)

    def test_register_and_apply_visual_template_from_raw_visual_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Dashboard")

            spec_path = root / "hero.yaml"
            spec_path.write_text(
                "\n".join(
                    [
                        "type: cardVisual",
                        "size: 260 x 120",
                        "title:",
                        "  show: true",
                        "  text: '{{ title }}'",
                        "bindings:",
                        "  Value: '{{ value }}'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            register_visual_template(
                project,
                spec_path,
                name="hero-card",
                category="kpi",
                tags=["card"],
            )
            visual, template = apply_visual_template(
                project,
                page,
                "hero-card",
                x=40,
                y=80,
                params={"title": "Revenue", "value": "Sales.Revenue"},
            )

            self.assertEqual(template.name, "hero-card")
            self.assertEqual(visual.visual_type, "cardVisual")
            self.assertEqual(visual.position["x"], 40)
            self.assertEqual(visual.position["y"], 80)
            self.assertEqual(project.get_bindings(visual), [("Data", "Sales", "Revenue", "column")])

    def test_visual_template_binds_measures_correctly_with_model(self) -> None:
        """Measures resolved via the semantic model use the Measure discriminator."""
        from tests.cli_regressions_support import write_model_table

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
    column Revenue
        dataType: int64
    measure 'Total Revenue'
        expression: SUM(Sales[Revenue])
""",
            )
            page = project.create_page("Dashboard")

            spec_path = root / "kpi.yaml"
            spec_path.write_text(
                "\n".join(
                    [
                        "type: cardVisual",
                        "size: 260 x 120",
                        "bindings:",
                        "  Value: '{{ value }}'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            register_visual_template(project, spec_path, name="kpi-card", category="kpi")

            # Bind to a measure — should use "measure" discriminator
            visual_m, _ = apply_visual_template(
                project, page, "kpi-card",
                params={"value": "Sales.Total Revenue"},
            )
            self.assertEqual(
                project.get_bindings(visual_m),
                [("Data", "Sales", "Total Revenue", "measure")],
            )

            # Bind to a column — should use "column" discriminator
            visual_c, _ = apply_visual_template(
                project, page, "kpi-card",
                params={"value": "Sales.Revenue"},
            )
            self.assertEqual(
                project.get_bindings(visual_c),
                [("Data", "Sales", "Revenue", "column")],
            )

    def test_get_catalog_item_rejects_ambiguous_plain_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            project.create_visual(page, "cardVisual")

            create_style(project, "shared", {"border.show": True})
            save_template(project, page, "shared")

            with self.assertRaises(ValueError):
                get_catalog_item(project, "shared")

            item = get_catalog_item(project, "style/shared")
            self.assertEqual(item.kind, "style")
            self.assertEqual(item.name, "shared")

    def test_validate_catalog_reports_invalid_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            styles_dir = root / ".pbi-styles"
            styles_dir.mkdir(parents=True, exist_ok=True)
            (styles_dir / "broken.yaml").write_text("name: [broken\n", encoding="utf-8")

            issues = validate_catalog(project, kind="style", scope="project")

            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].kind, "style")
            self.assertIn("not valid YAML", issues[0].message)

    def test_validate_catalog_reports_invalid_visual_template_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            vt_dir = root / ".pbi-catalog" / "visual"
            vt_dir.mkdir(parents=True, exist_ok=True)
            (vt_dir / "broken.yaml").write_text(
                "\n".join(
                    [
                        "kind: visual",
                        "name: broken",
                        "payload:",
                        "  title:",
                        "    show: true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            issues = validate_catalog(project, kind="visual", scope="project")
            self.assertEqual(len(issues), 1)
            self.assertIn('must include a non-empty "type"', issues[0].message)

    def test_old_kind_aliases_resolve_to_new_catalog_kinds(self) -> None:
        items = list_catalog_items(None, kind="visual-template")
        refs = {(item.kind, item.name, item.scope) for item in items}
        self.assertIn(("visual", "hero-kpi-card", "bundled"), refs)

    def test_bundled_assets_stamp_without_schema_or_role_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Audit")

            for template in list_visual_templates(project):
                if template.scope != "bundled":
                    continue
                visual, _template = apply_visual_template(project, page, template.name)
                query_roles = set(
                    visual.data.get("visual", {}).get("query", {}).get("queryState", {}).keys()
                )
                schema_roles = set((get_data_roles(visual.visual_type) or {}).keys())
                self.assertTrue(
                    query_roles <= schema_roles,
                    f'{template.name} stamped unsupported query roles: {sorted(query_roles - schema_roles)}',
                )

            for component in list_components(project):
                if component.scope != "bundled":
                    continue
                created = apply_component(project, page, component.name)
                child_visuals = (
                    created[:-1]
                    if len(created) >= 2 and "visualGroup" in created[-1].data
                    else created
                )
                for spec, visual in zip(component.visuals, child_visuals):
                    query_roles = set(
                        visual.data.get("visual", {}).get("query", {}).get("queryState", {}).keys()
                    )
                    schema_roles = set((get_data_roles(visual.visual_type) or {}).keys())
                    self.assertTrue(
                        query_roles <= schema_roles,
                        f'{component.name}/{spec.get("name")} stamped unsupported query roles: '
                        f'{sorted(query_roles - schema_roles)}',
                    )

            schema_issues = [
                issue.message
                for issue in validate_project(project)
                if issue.message.startswith("Schema:")
            ]
            self.assertEqual(schema_issues, [])


class CatalogCliTests(unittest.TestCase):
    def test_catalog_list_visual_templates_includes_bundled_items(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["catalog", "list", "--kind", "visual", "--json"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        rows = json.loads(result.stdout)
        names = {row["name"] for row in rows}
        self.assertIn("hero-kpi-card", names)

    def test_catalog_list_and_get_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch("pathlib.Path.home", return_value=home):
                project = make_project(root)
                page = project.create_page("Demo")
                project.create_visual(page, "cardVisual")

                create_style(project, "local-style", {"border.show": True})
                create_style(None, "global-style", {"title.show": True}, global_scope=True)

                result = runner.invoke(
                    app,
                    ["catalog", "list", "--kind", "style", "--json", "--project", str(root / "Sample.pbip")],
                )

                self.assertEqual(result.exit_code, 0, result.stdout)
                rows = json.loads(result.stdout)
                names = {row["name"] for row in rows}
                self.assertIn("local-style", names)
                self.assertIn("global-style", names)

                get_result = runner.invoke(
                    app,
                    ["catalog", "get", "style/local-style", "--project", str(root / "Sample.pbip")],
                )
                self.assertEqual(get_result.exit_code, 0, get_result.stdout)
                self.assertIn("name: local-style", get_result.stdout)

    def test_catalog_register_and_apply_visual_template_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Dashboard")
            spec_path = root / "hero.yaml"
            spec_path.write_text(
                "\n".join(
                    [
                        "type: cardVisual",
                        "size: 260 x 120",
                        "title:",
                        "  show: true",
                        "  text: '{{ title }}'",
                        "bindings:",
                        "  Value: '{{ value }}'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            register_result = runner.invoke(
                app,
                [
                    "catalog",
                    "register",
                    str(spec_path),
                    "--kind",
                    "visual",
                    "--name",
                    "hero-card",
                    "--category",
                    "kpi",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(register_result.exit_code, 0, register_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "catalog",
                    "apply",
                    "visual/hero-card",
                    "Dashboard",
                    "--x",
                    "24",
                    "--y",
                    "48",
                    "--name",
                    "revenueHero",
                    "--set",
                    "title=Revenue",
                    "--set",
                    "value=Sales.Revenue",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Dashboard")
            visual = reloaded.find_visual(page, "revenueHero")
            self.assertEqual(visual.position["x"], 24)
            self.assertEqual(visual.position["y"], 48)
            self.assertEqual(reloaded.get_bindings(visual), [("Data", "Sales", "Revenue", "column")])

    def test_catalog_create_visual_template_from_existing_visual_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Dashboard")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "revenueCard"
            visual.save()
            project.add_binding(visual, "Value", "Sales", "Revenue")

            result = runner.invoke(
                app,
                [
                    "catalog",
                    "create",
                    "visual",
                    "--from-visual",
                    "Dashboard",
                    "--visual",
                    "revenueCard",
                    "--name",
                    "revenue-card-template",
                    "--category",
                    "kpi",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            template_path = root / ".pbi-catalog" / "visual" / "revenue-card-template.yaml"
            self.assertTrue(template_path.exists())
            content = template_path.read_text(encoding="utf-8")
            self.assertIn("kind: visual", content)
            self.assertNotIn("id:", content)

    def test_catalog_clone_and_delete_visual_template_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch("pathlib.Path.home", return_value=home):
                project = make_project(root)
                page = project.create_page("Dashboard")
                visual = project.create_visual(page, "cardVisual")
                visual.data["name"] = "cardA"
                visual.save()

                create_result = runner.invoke(
                    app,
                    [
                        "catalog",
                        "create",
                        "visual",
                        "--from-visual",
                        "Dashboard",
                        "--visual",
                        "cardA",
                        "--name",
                        "card-template",
                        "--project",
                        str(root / "Sample.pbip"),
                    ],
                )
                self.assertEqual(create_result.exit_code, 0, create_result.stdout)

                clone_result = runner.invoke(
                    app,
                    [
                        "catalog",
                        "clone",
                        "visual/card-template",
                        "--to-global",
                        "--name",
                        "card-template-global",
                        "--project",
                        str(root / "Sample.pbip"),
                    ],
                )
                self.assertEqual(clone_result.exit_code, 0, clone_result.stdout)
                self.assertTrue((home / ".config" / "pbi" / "catalog" / "visual" / "card-template-global.yaml").exists())

                delete_result = runner.invoke(
                    app,
                    [
                        "catalog",
                        "delete",
                        "visual/card-template",
                        "--force",
                        "--project",
                        str(root / "Sample.pbip"),
                    ],
                )
                self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
                self.assertFalse((root / ".pbi-catalog" / "visual" / "card-template.yaml").exists())

    def test_catalog_delete_rejects_bundled_items(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["catalog", "delete", "visual/hero-kpi-card", "--force"],
        )
        self.assertEqual(result.exit_code, 1, result.stdout)
        self.assertIn("immutable", result.stdout)

    def test_catalog_create_and_apply_style_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Dashboard")
            source = project.create_visual(page, "cardVisual")
            source.data["name"] = "sourceCard"
            set_property(source.data, "border.show", "true", VISUAL_PROPERTIES)
            set_property(source.data, "border.radius", "8", VISUAL_PROPERTIES)
            source.save()
            target = project.create_visual(page, "cardVisual")
            target.data["name"] = "targetCard"
            target.save()

            create_result = runner.invoke(
                app,
                [
                    "catalog",
                    "create",
                    "style",
                    "--from-visual",
                    "Dashboard",
                    "--visual",
                    "sourceCard",
                    "--name",
                    "card-style",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "catalog",
                    "apply",
                    "style/card-style",
                    "Dashboard",
                    "--visual",
                    "targetCard",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            self.assertIn('Applied style "card-style"', apply_result.stdout)
            reloaded = Project.find(root / "Sample.pbip")
            reloaded_page = reloaded.find_page("Dashboard")
            updated = reloaded.find_visual(reloaded_page, "targetCard")
            self.assertTrue(get_property(updated.data, "border.show", VISUAL_PROPERTIES))

    def test_catalog_create_and_apply_page_template_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = project.create_page("Source")
            target = project.create_page("Landing")
            visual = project.create_visual(source, "cardVisual")
            visual.data["name"] = "revenueCard"
            visual.save()

            create_result = runner.invoke(
                app,
                [
                    "catalog",
                    "create",
                    "page",
                    "--from-visual",
                    "Source",
                    "--name",
                    "landing-template",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "catalog",
                    "apply",
                    "page/landing-template",
                    "Landing",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            reloaded = Project.find(root / "Sample.pbip")
            landing = reloaded.find_page("Landing")
            applied = reloaded.find_visual(landing, "revenueCard")
            self.assertEqual(applied.visual_type, "cardVisual")

    def test_catalog_create_and_apply_component_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = project.create_page("Source")
            target = project.create_page("Target")
            one = project.create_visual(source, "textbox", x=0, y=0, width=100, height=30)
            one.data["name"] = "titleBox"
            one.save()
            two = project.create_visual(source, "shape", x=0, y=40, width=120, height=50)
            two.data["name"] = "bgShape"
            two.save()
            project.create_group(source, [one, two], display_name="Header Group")

            create_result = runner.invoke(
                app,
                [
                    "catalog",
                    "create",
                    "component",
                    "--from-visual",
                    "Source",
                    "--visual",
                    "Header-Group",
                    "--name",
                    "page-header",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "catalog",
                    "apply",
                    "component/page-header",
                    "Target",
                    "--x",
                    "16",
                    "--y",
                    "24",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            reloaded = Project.find(root / "Sample.pbip")
            target_page = reloaded.find_page("Target")
            visuals = reloaded.get_visuals(target_page)
            self.assertGreaterEqual(len(visuals), 2)

    def test_component_apply_deduplicates_visual_names(self) -> None:
        """Applying a component with a name that already exists on the page auto-suffixes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Dashboard")

            # Pre-existing visual with same name as what the component will produce
            existing = project.create_visual(page, "textbox", x=0, y=0, width=100, height=30)
            existing.data["name"] = "titleBox"
            existing.save()

            comp_yaml = root / "header.yaml"
            comp_yaml.write_text(
                "\n".join(
                    [
                        "visuals:",
                        "- type: textbox",
                        "  name: titleBox",
                        "  position: 0, 0",
                        "  size: 100 x 30",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            save_component_from_yaml(project, comp_yaml, "header")
            created = apply_component(project, page, "header", x=200, y=0)

            names = [v.name for v in project.get_visuals(page)]
            self.assertIn("titleBox", names)
            self.assertIn("titleBox-2", names)
            self.assertEqual(len(names), len(set(names)), "All visual names must be unique")

    def test_catalog_register_component_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Target")
            component_yaml = root / "header.yaml"
            component_yaml.write_text(
                "\n".join(
                    [
                        "visuals:",
                        "- type: textbox",
                        "  name: titleBox",
                        "  position: 0, 0",
                        "  size: 100 x 30",
                        "- type: shape",
                        "  name: bgShape",
                        "  position: 0, 40",
                        "  size: 120 x 50",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            register_result = runner.invoke(
                app,
                [
                    "catalog",
                    "register",
                    str(component_yaml),
                    "--kind",
                    "component",
                    "--name",
                    "page-header",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(register_result.exit_code, 0, register_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "catalog",
                    "apply",
                    "component/page-header",
                    "Target",
                    "--x",
                    "16",
                    "--y",
                    "24",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            reloaded = Project.find(root / "Sample.pbip")
            target_page = reloaded.find_page("Target")
            visuals = reloaded.get_visuals(target_page)
            self.assertGreaterEqual(len(visuals), 2)

    def test_catalog_validate_cli_fails_on_invalid_asset(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            styles_dir = root / ".pbi-styles"
            styles_dir.mkdir(parents=True, exist_ok=True)
            (styles_dir / "broken.yaml").write_text("name: [broken\n", encoding="utf-8")

            result = runner.invoke(
                app,
                ["catalog", "validate", "--kind", "style", "--scope", "project", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Style "broken" is not valid', result.stdout)

    def test_legacy_component_commands_are_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["component", "list"])
        self.assertNotEqual(result.exit_code, 0)

    def test_legacy_style_commands_are_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["style", "list"])
        self.assertNotEqual(result.exit_code, 0)

    def test_legacy_page_template_commands_are_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["page", "template", "list"])
        self.assertNotEqual(result.exit_code, 0)
