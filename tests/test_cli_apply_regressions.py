from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.cli import app
from pbi.export import export_yaml
from pbi.project import Project
from pbi.validate import validate_project
from tests.cli_regressions_support import make_project, write_model_table


class ApplyWorkflowRegressionTests(unittest.TestCase):
    def test_apply_name_only_page_spec_skips_definition_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [{"name": "Demo"}],
                },
                sort_keys=False,
            )

            with mock.patch("pbi.apply.shutil.copytree", wraps=shutil.copytree) as copytree_mock:
                result = apply_yaml(project, yaml_content)

            self.assertEqual(result.errors, [])
            self.assertEqual(copytree_mock.call_count, 0)

    def test_apply_noop_page_update_skips_definition_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo", width=1280, height=720)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "width": 1280,
                            "height": 720,
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("pbi.apply.shutil.copytree", wraps=shutil.copytree) as copytree_mock:
                result = apply_yaml(project, yaml_content)

            self.assertEqual(result.errors, [])
            self.assertEqual(copytree_mock.call_count, 0)

    def test_apply_error_only_page_update_skips_definition_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "notARealProperty": {"bogus": True},
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("pbi.apply.shutil.copytree", wraps=shutil.copytree) as copytree_mock:
                result = apply_yaml(project, yaml_content)

            self.assertTrue(result.errors)
            self.assertEqual(copytree_mock.call_count, 0)

    def test_apply_accepts_stdin_with_dash(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "From stdin",
                            "visuals": [],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["apply", "-", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            applied = Project.find(root / "Sample.pbip")
            applied.find_page("From stdin")

    def test_apply_accepts_piped_stdin_without_file_argument(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Piped apply",
                            "visuals": [],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["apply", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            applied = Project.find(root / "Sample.pbip")
            applied.find_page("Piped apply")

    def test_raw_pbir_visual_still_accepts_human_readable_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "textSlicer", x=10, y=20, width=300, height=120)
            source.add_binding(visual, "Values", "Customers", "Region")

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported_visual = spec["pages"][0]["visuals"][0]
            exported_visual["isHidden"] = True
            exported_visual["bindings"] = {"Values": "Sales.Region"}

            target = make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))

            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.get_visuals(page)[0]
            self.assertTrue(visual.data.get("isHidden"))
            self.assertEqual(
                visual.data["visual"]["query"]["queryState"]["Values"]["projections"][0]["queryRef"],
                "Sales.Region",
            )

    def test_overwrite_apply_rolls_back_on_failure(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer", x=1, y=2, width=100, height=50)
            visual.data["name"] = "keepme"
            visual.save()

            spec_path = root / "invalid.yaml"
            spec_path.write_text(
                """\
version: 1
pages:
- name: Demo
  visuals:
  - name: replacement
    type: textSlicer
    position: 0, 0
    size: 100 x 50
    notARealProperty:
      bogus: true
""",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["apply", str(spec_path), "--overwrite", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            visuals = restored.get_visuals(page)
            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0].name, "keepme")

    def test_apply_rolls_back_on_failure_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "card1",
                                    "position": "99, 88",
                                    "notARealProperty": {"bogus": True},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(result.errors)

            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            updated = restored.find_visual(page, "card1")
            self.assertEqual(updated.position["x"], 10)
            self.assertEqual(updated.position["y"], 20)

    def test_apply_type_conversion_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer", x=5, y=7, width=100, height=50)
            visual.data["name"] = "vis1"
            visual.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "vis1",
                                    "type": "cardVisual",
                                    "position": "77, 66",
                                    "notARealProperty": {"bogus": True},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(result.errors)

            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            updated = restored.find_visual(page, "vis1")
            self.assertEqual(updated.visual_type, "textSlicer")
            self.assertEqual(updated.position["x"], 5)
            self.assertEqual(updated.position["y"], 7)

    def test_apply_rolls_back_on_chart_schema_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "badchart",
                                    "type": "clusteredColumnChart",
                                    "chart:legnd.show": True,
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content)

            self.assertTrue(result.errors)
            self.assertTrue(result.rolled_back)
            self.assertTrue(any("Schema:" in error for error in result.errors))

            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_apply_rolls_back_on_raw_pbir_schema_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported_visual = spec["pages"][0]["visuals"][0]
            exported_visual["pbir"] = copy.deepcopy(visual.data)
            exported_visual["pbir"].setdefault("visual", {}).setdefault("objects", {})["legnd"] = [
                {
                    "properties": {
                        "show": {
                            "expr": {
                                "Literal": {
                                    "Value": "true",
                                }
                            }
                        }
                    }
                }
            ]

            target = make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))

            self.assertTrue(result.errors)
            self.assertTrue(result.rolled_back)
            self.assertTrue(
                any("Post-apply validation:" in error and "Schema:" in error for error in result.errors)
            )

            restored = Project.find(root / "target" / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_overwrite_backup_filename_is_sanitized(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("../../outside")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            visual.save()

            spec_path = root / "escape.yaml"
            spec_path.write_text(
                """\
version: 1
pages:
- name: ../../outside
  visuals:
  - name: card1
    notARealProperty:
      bogus: true
""",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["apply", str(spec_path), "--overwrite", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertFalse((root / "outside.yaml").exists())
            backups = list(root.glob(".pbi-backup-*.yaml"))
            self.assertEqual(len(backups), 1)

class ValidationPerformanceRegressionTests(unittest.TestCase):
    def test_validate_project_reuses_loaded_json_without_project_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            with mock.patch.object(project, "get_pages", side_effect=AssertionError("unexpected project rescan")), \
                 mock.patch.object(project, "get_visuals", side_effect=AssertionError("unexpected project rescan")):
                issues = validate_project(project)

            self.assertEqual(issues, [])

class YamlStdinWorkflowRegressionTests(unittest.TestCase):
    def test_diff_accepts_stdin_with_dash(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "New from stdin",
                            "visuals": [],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["diff", "-", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("+ New page:", result.stdout)
            self.assertIn("New from stdin", result.stdout)

    def test_diff_accepts_piped_stdin_without_file_argument(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Piped diff",
                            "visuals": [],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["diff", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("+ New page:", result.stdout)
            self.assertIn("Piped diff", result.stdout)

    def test_model_apply_accepts_stdin_with_dash(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            table_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )

            yaml_content = yaml.safe_dump(
                {
                    "measures": {
                        "Sales": [
                            {
                                "name": "Total Revenue",
                                "expression": "SUM ( Sales[Revenue] )",
                                "format": "0",
                            }
                        ]
                    }
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["model", "apply", "-", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created measure", result.stdout)
            self.assertIn("Total Revenue", table_path.read_text(encoding="utf-8"))

    def test_model_apply_accepts_piped_stdin_without_file_argument(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            table_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )

            yaml_content = yaml.safe_dump(
                {
                    "measures": {
                        "Sales": [
                            {
                                "name": "Total Revenue",
                                "expression": "SUM ( Sales[Revenue] )",
                                "format": "0",
                            }
                        ]
                    }
                },
                sort_keys=False,
            )

            result = runner.invoke(
                app,
                ["model", "apply", "--project", str(root / "Sample.pbip")],
                input=yaml_content,
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created measure", result.stdout)
            self.assertIn("Total Revenue", table_path.read_text(encoding="utf-8"))

class TestApplyPerformance(unittest.TestCase):
    def test_apply_interactions_use_page_local_visual_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            source = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            source.data["name"] = "card1"
            source.save()
            target = project.create_visual(page, "cardVisual", x=120, y=20, width=100, height=50)
            target.data["name"] = "card2"
            target.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {"name": "card1"},
                                {"name": "card2"},
                            ],
                            "interactions": [
                                {"source": "card1", "target": "card2", "type": "NoFilter"},
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch.object(project, "find_visual", wraps=project.find_visual) as find_visual_mock:
                result = apply_yaml(project, yaml_content)

            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")
            self.assertEqual(find_visual_mock.call_count, 0)

    def test_apply_reuses_semantic_model_for_bindings_and_filters(self) -> None:
        from pbi.modeling.schema import SemanticModel

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "table1",
                                    "type": "tableEx",
                                    "bindings": {
                                        "Values": [
                                            "Customers.Region",
                                            "Customers.Region",
                                        ]
                                    },
                                    "filters": [
                                        {
                                            "field": "Customers.Region",
                                            "type": "Include",
                                            "values": ["West"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("pbi.modeling.schema.SemanticModel.load", wraps=SemanticModel.load) as load_mock:
                result = apply_yaml(project, yaml_content)

            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")
            self.assertEqual(load_mock.call_count, 1)

    def test_apply_bindings_prunes_unbound_column_selector_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            customers_table = root / "Sample.SemanticModel" / "definition" / "tables" / "Customers.tmdl"
            customers_table.write_text(
                "\n".join(
                    [
                        "table Customers",
                        "\tcolumn Region",
                        "\t\tdataType: string",
                        "\t\tlineageTag: c-1",
                        "\t\tsummarizeBy: none",
                        "\t\tsourceColumn: Region",
                        "",
                        "\tcolumn Segment",
                        "\t\tdataType: string",
                        "\t\tlineageTag: c-2",
                        "\t\tsummarizeBy: none",
                        "\t\tsourceColumn: Segment",
                    ]
                ) + "\n",
                encoding="utf-8",
            )
            page = project.create_page("Demo")
            visual = project.create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            project.add_binding(visual, "Values", "Customers", "Region")
            project.add_binding(visual, "Values", "Customers", "Segment")
            visual.data["visual"].setdefault("objects", {})["columnWidth"] = [
                {
                    "selector": {"metadata": "Customers.Region"},
                    "properties": {"value": {"expr": {"Literal": {"Value": "200D"}}}},
                },
                {
                    "selector": {"metadata": "Customers.Segment"},
                    "properties": {"value": {"expr": {"Literal": {"Value": "300D"}}}},
                },
            ]
            visual.data["visual"]["objects"]["columnFormatting"] = [
                {"selector": {"metadata": "Customers.Region"}},
                {"selector": {"metadata": "Customers.Segment"}},
            ]
            visual.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "table1",
                                    "type": "tableEx",
                                    "bindings": {"Values": ["Customers.Region"]},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content, overwrite=True)
            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")

            project.clear_caches()
            updated = project.find_visual(project.find_page("Demo"), "table1")
            column_width = updated.data["visual"]["objects"]["columnWidth"]
            self.assertEqual(len(column_width), 1)
            self.assertEqual(column_width[0]["selector"]["metadata"], "Customers.Region")
            column_formatting = updated.data["visual"]["objects"]["columnFormatting"]
            self.assertEqual(len(column_formatting), 1)
            self.assertEqual(column_formatting[0]["selector"]["metadata"], "Customers.Region")
