from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest
import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.cli import app
from pbi.export import export_yaml
from pbi.project import Project
from pbi.report_authoring import ReportAuthoring
from tests.support import make_project, write_model_table


class ApplyWorkflowRegressionTests(unittest.TestCase):
    def test_raw_pbir_visual_still_accepts_human_readable_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_project(root / "source")
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "textSlicer", x=10, y=20, width=300, height=120)
            ReportAuthoring(source).add_binding(visual, "Values", "Customers", "Region")

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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "textSlicer", x=1, y=2, width=100, height=50)
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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
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

    def test_apply_type_conversion_with_reused_visual_id_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "textSlicer", x=5, y=7, width=100, height=50)
            visual.data["name"] = "vis1"
            visual.save()
            before = (visual.folder / "visual.json").read_bytes()

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

            with mock.patch("secrets.token_hex", return_value=visual.folder.name):
                result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(result.errors)

            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            updated = restored.find_visual(page, "vis1")
            self.assertEqual(updated.visual_type, "textSlicer")
            self.assertEqual((updated.folder / "visual.json").read_bytes(), before)

    def test_apply_type_conversion_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "textSlicer", x=5, y=7, width=100, height=50)
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
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
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
            page = ReportAuthoring(project).create_page("../../outside")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual")
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

PAGE_SPEC = yaml.safe_dump({"version": 1, "pages": [{"name": "From stdin", "visuals": []}]}, sort_keys=False)
MEASURE_SPEC = yaml.safe_dump(
    {"measures": {"Sales": [{"name": "Total Revenue", "expression": "SUM ( Sales[Revenue] )", "format": "0"}]}},
    sort_keys=False,
)
SALES_TABLE = """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
"""


def _check_apply(root: Path, output: str) -> None:
    Project.find(root / "Sample.pbip").find_page("From stdin")


def _check_diff(root: Path, output: str) -> None:
    assert "+ New page:" in output
    assert "From stdin" in output


def _check_model_apply(root: Path, output: str) -> None:
    assert "Created measure" in output
    tmdl = root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
    assert "Total Revenue" in tmdl.read_text(encoding="utf-8")


@pytest.mark.parametrize("dash", [True, False], ids=["dash", "piped"])
@pytest.mark.parametrize(
    ("command", "spec", "check"),
    [
        (["apply"], PAGE_SPEC, _check_apply),
        (["diff"], PAGE_SPEC, _check_diff),
        (["model", "apply"], MEASURE_SPEC, _check_model_apply),
    ],
    ids=["apply", "diff", "model-apply"],
)
def test_yaml_commands_read_stdin(tmp_path: Path, command: list[str], spec: str, check, dash: bool) -> None:
    """``apply``, ``diff`` and ``model apply`` read YAML from ``-`` or a pipe."""
    make_project(tmp_path)
    write_model_table(tmp_path, "Sales.tmdl", SALES_TABLE)
    args = [*command, *(["-"] if dash else []), "--project", str(tmp_path / "Sample.pbip")]

    result = CliRunner().invoke(app, args, input=spec)

    assert result.exit_code == 0, result.stdout
    check(tmp_path, result.stdout)


class ApplyBindingPruneTests(unittest.TestCase):
    def test_apply_bindings_prunes_unbound_column_selector_metadata(self) -> None:
        # Guessed shape: the bare ``columnFormatting`` selector marker below has
        # no Desktop sample, so its write shape is not verified (#85).
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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            ReportAuthoring(project).add_binding(visual, "Values", "Customers", "Region")
            ReportAuthoring(project).add_binding(visual, "Values", "Customers", "Segment")
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


class ApplyExactVisualMatchTests(unittest.TestCase):
    """apply and diff match visuals by ID or exact name only (#32)."""

    def _project_with_slicer(self, root: Path) -> Project:
        project = make_project(root)
        result = apply_yaml(project, self._yaml([
            {"name": "slicerRegion", "type": "slicer"},
            {"name": "Revenue Card", "type": "card"},
        ]))
        self.assertEqual(result.errors, [])
        return project

    def _visuals(self, project: Project) -> dict[str, str]:
        page = project.find_page("Demo")
        return {visual.name: visual.visual_type for visual in project.get_visuals(page)}

    def _yaml(self, visuals: list[dict], **page: object) -> str:
        return yaml.safe_dump(
            {"version": 1, "pages": [{"name": "Demo", **page, "visuals": visuals}]}, sort_keys=False
        )

    def test_name_contained_in_existing_name_creates_new_visual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_slicer(Path(tmp))
            result = apply_yaml(project, self._yaml([{"name": "region", "type": "donutChart"}]))

            self.assertEqual(result.errors, [])
            self.assertEqual(result.visuals_created, [("Demo", "region")])
            visuals = self._visuals(project)
            self.assertEqual(visuals["slicerRegion"], "slicer")
            self.assertEqual(visuals["region"], "donutChart")

    def test_index_and_type_names_do_not_match_existing_visuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_slicer(Path(tmp))
            result = apply_yaml(project, self._yaml([
                {"name": "1", "type": "textbox"},
                {"name": "card", "type": "card"},
            ]))

            self.assertEqual(result.errors, [])
            visuals = self._visuals(project)
            self.assertEqual(visuals["slicerRegion"], "slicer")
            self.assertEqual(len(visuals), 4)

    def test_reapplying_a_spaced_name_updates_the_sanitized_visual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_slicer(Path(tmp))
            spec = self._yaml([{"name": "Sales Chart", "type": "clusteredColumnChart"}])
            apply_yaml(project, spec)
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.visuals_created, [])
            self.assertEqual(sorted(self._visuals(project)), ["Revenue-Card", "Sales-Chart", "slicerRegion"])

    def test_interaction_with_partial_name_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_slicer(Path(tmp))
            result = apply_yaml(project, self._yaml(
                [], interactions=[{"source": "Region", "target": "Revenue-Card", "type": "NoFilter"}],
            ))

            self.assertEqual(len(result.errors), 1)
            self.assertIn('Visual "Region" not found', result.errors[0])
            self.assertIn('"slicerRegion"', result.errors[0])

    def test_diff_shows_contained_name_as_new_visual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project_with_slicer(root)
            spec = root / "spec.yaml"
            spec.write_text(self._yaml([{"name": "region", "type": "donutChart"}]), encoding="utf-8")

            result = CliRunner().invoke(app, ["diff", str(spec), "-p", str(root)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("New visual: region", result.output)

    def test_diff_matches_id_against_folder_ids_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._project_with_slicer(root)
            spec_yaml = self._yaml([{"id": "Revenue-Card", "name": "profitCard", "type": "card"}])
            spec = root / "spec.yaml"
            spec.write_text(spec_yaml, encoding="utf-8")

            result = CliRunner().invoke(app, ["diff", str(spec), "-p", str(root)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("New visual: profitCard", result.output)
            # apply agrees: the id is not a folder, so profitCard is created.
            self.assertEqual(apply_yaml(project, spec_yaml).visuals_created, [("Demo", "profitCard")])
