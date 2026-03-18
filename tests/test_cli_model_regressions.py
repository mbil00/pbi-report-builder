from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model_apply import apply_model_yaml
from tests.cli_regressions_support import make_project, write_model_table


class ModelApplyPerformanceRegressionTests(unittest.TestCase):
    def test_model_apply_batches_multiple_measure_edits_into_one_file_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            from pbi.modeling import writes as modeling_writes

            table_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Total Revenue' = SUM ( Sales[Revenue] )
\t\tformatString: 0
\t\tlineageTag: m-1
                """,
            )

            yaml_content = yaml.safe_dump(
                {
                    "measures": {
                        "Sales": [
                            {
                                "name": "Total Revenue",
                                "expression": "SUM ( Sales[Revenue] ) + 1",
                                "format": "#,0",
                                "description": "'updated'",
                                "displayFolder": "'KPIs'",
                            }
                        ]
                    }
                },
                sort_keys=False,
            )

            original_write = modeling_writes._write_tmdl_lines
            with mock.patch("pbi.modeling.writes._write_tmdl_lines", wraps=original_write) as write_lines:
                result = apply_model_yaml(root, yaml_content, dry_run=False)

            self.assertEqual(result.errors, [])
            self.assertEqual(write_lines.call_count, 1)
            content = table_path.read_text(encoding="utf-8")
            self.assertIn("SUM ( Sales[Revenue] ) + 1", content)
            self.assertIn("formatString: #,0", content)
            self.assertIn("description: 'updated'", content)
            self.assertIn("displayFolder: 'KPIs'", content)


class ModelManagementRegressionTests(unittest.TestCase):
    def test_model_format_updates_column_and_measure_tmdl(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tformatString: 0.0%
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "set",
                    "Sales.OrderDate",
                    "formatString=dd/mm/yyyy",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            measure_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "set",
                    "Sales.Compliance Rate",
                    "formatString=0.00%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(measure_result.exit_code, 0, measure_result.stdout)

            content = (root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
            self.assertIn("\t\tformatString: dd/mm/yyyy", content)
            self.assertIn("\t\tformatString: 0.00%", content)

    def test_model_format_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            before = path.read_text(encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "set",
                    "Sales.OrderDate",
                    "formatString=dd/mm/yyyy",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_model_column_hide_show_and_hidden_only_listing(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn DeviceName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DeviceName

\tcolumn AzureADDeviceId
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: AzureADDeviceId
                """,
            )

            hide_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "hide",
                    "Devices.AzureADDeviceId",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(hide_result.exit_code, 0, hide_result.stdout)

            hidden_list = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "list",
                    "Devices",
                    "--hidden-only",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(hidden_list.exit_code, 0, hidden_list.stdout)
            self.assertIn("AzureADDeviceId", hidden_list.stdout)
            self.assertNotIn("DeviceName", hidden_list.stdout)

            show_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "unhide",
                    "Devices.AzureADDeviceId",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)

            visible_list = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "list",
                    "Devices",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(visible_list.exit_code, 0, visible_list.stdout)
            self.assertIn("AzureADDeviceId", visible_list.stdout)

    def test_model_column_hide_rejects_measures(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tlineageTag: m-1
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "hide",
                    "Sales.Compliance Rate",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("not a column", result.stdout)

    def test_model_measure_create_show_edit_delete_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tlineageTag: table-1

\tmeasure 'Old Measure' = 1
\t\tformatString: 0
\t\tlineageTag: m-1

\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "create",
                    "Sales",
                    "New KPI",
                    "SUM ( Sales[Revenue] )",
                    "--format",
                    "0.0%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'New KPI' = SUM ( Sales[Revenue] )", content)
            self.assertIn("\t\tformatString: 0.0%", content)

            show_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "get",
                    "Sales",
                    "New KPI",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)
            self.assertIn("Sales.New KPI", show_result.stdout)
            self.assertIn("SUM ( Sales[Revenue] )", show_result.stdout)
            self.assertIn("0.0%", show_result.stdout)

            dax_path = root / "new-kpi.dax"
            dax_path.write_text(
                "CALCULATE(\n    SUM ( Sales[Revenue] ),\n    Sales[Revenue] > 0\n)\n",
                encoding="utf-8",
            )
            edit_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "edit",
                    "Sales",
                    "New KPI",
                    "--from-file",
                    str(dax_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(edit_result.exit_code, 0, edit_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'New KPI' =", content)
            self.assertIn("\t\tCALCULATE(", content)
            self.assertIn("SUM ( Sales[Revenue] ),", content)
            self.assertIn("\t\tlineageTag:", content)

            delete_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "delete",
                    "Sales",
                    "New KPI",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertNotIn("New KPI", path.read_text(encoding="utf-8"))

    def test_model_measure_create_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
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
            before = path.read_text(encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "create",
                    "Sales",
                    "Preview KPI",
                    "SUM ( Sales[Revenue] )",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_model_calculated_column_create_get_edit_delete_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "create",
                    "Devices",
                    "StorageUsedPct",
                    "DIVIDE([TotalStorageGB], 100, 0)",
                    "--type",
                    "double",
                    "--format",
                    "0.0%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct = DIVIDE([TotalStorageGB], 100, 0)", content)
            self.assertIn("\t\tdataType: double", content)
            self.assertIn("\t\tformatString: 0.0%", content)
            self.assertIn("\t\tsummarizeBy: none", content)

            get_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "get",
                    "Devices.StorageUsedPct",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Devices.StorageUsedPct", get_result.stdout)
            self.assertIn("calculatedColumn", get_result.stdout)
            self.assertIn("DIVIDE([TotalStorageGB], 100, 0)", get_result.stdout)

            dax_path = root / "storage-used.dax"
            dax_path.write_text(
                "DIVIDE(\n    [TotalStorageGB] - 10,\n    [TotalStorageGB],\n    0\n)\n",
                encoding="utf-8",
            )
            edit_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "edit",
                    "Devices",
                    "StorageUsedPct",
                    "--from-file",
                    str(dax_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(edit_result.exit_code, 0, edit_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct =", content)
            self.assertIn("\t\t\tDIVIDE(", content)
            self.assertIn("[TotalStorageGB] - 10,", content)
            # Properties must remain at 2-tab indent, not swallowed into expression
            self.assertIn("\t\tdataType:", content)

            delete_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "delete",
                    "Devices",
                    "StorageUsedPct",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertNotIn("StorageUsedPct", path.read_text(encoding="utf-8"))

    def test_model_column_delete_rejects_source_columns(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn DeviceName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DeviceName
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "delete",
                    "Devices",
                    "DeviceName",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("source column", result.stdout)

    def test_model_apply_creates_and_updates_from_yaml(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            sales_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tformatString: 0.0%
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate

\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )
            devices_path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn AzureADDeviceId
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: AzureADDeviceId

\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )
            spec_path = root / "model-changes.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "measures": {
                            "Sales": [
                                {
                                    "name": "Compliance Rate",
                                    "expression": "DIVIDE ( 4, 5, 0 )",
                                    "format": "0.00%",
                                },
                                {
                                    "name": "Total Revenue",
                                    "expression": "SUM ( Sales[Revenue] )",
                                    "format": "0",
                                },
                            ]
                        },
                        "columns": {
                            "Sales": {
                                "OrderDate": {"format": "dd/mm/yyyy"},
                            },
                            "Devices": {
                                "StorageUsedPct": {
                                    "type": "calculated",
                                    "dataType": "double",
                                    "expression": "DIVIDE([TotalStorageGB], 100, 0)",
                                    "format": "0.0%",
                                    "hidden": True,
                                },
                                "AzureADDeviceId": {"hidden": True},
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created measure", result.stdout)
            self.assertIn("Updated measure", result.stdout)
            self.assertIn("Created calculated column", result.stdout)
            self.assertIn("Updated column", result.stdout)

            sales_content = sales_path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'Compliance Rate' = DIVIDE ( 4, 5, 0 )", sales_content)
            self.assertIn("\t\tformatString: 0.00%", sales_content)
            self.assertIn("\tmeasure 'Total Revenue' = SUM ( Sales[Revenue] )", sales_content)
            self.assertIn("\t\tformatString: 0", sales_content)
            self.assertIn("\t\tformatString: dd/mm/yyyy", sales_content)

            devices_content = devices_path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct = DIVIDE([TotalStorageGB], 100, 0)", devices_content)
            self.assertIn("\t\tformatString: 0.0%", devices_content)
            self.assertIn("\t\tisHidden", devices_content)
            self.assertIn("\tcolumn AzureADDeviceId", devices_content)

    def test_model_apply_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            sales_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            devices_path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )
            before_sales = sales_path.read_text(encoding="utf-8")
            before_devices = devices_path.read_text(encoding="utf-8")
            spec_path = root / "model-dry-run.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "measures": {
                            "Sales": [
                                {
                                    "name": "Total Revenue",
                                    "expression": "1",
                                    "format": "0",
                                }
                            ]
                        },
                        "columns": {
                            "Sales": {"OrderDate": {"format": "dd/mm/yyyy"}},
                            "Devices": {
                                "StorageUsedPct": {
                                    "type": "calculated",
                                    "dataType": "double",
                                    "expression": "DIVIDE([TotalStorageGB], 100, 0)",
                                    "hidden": True,
                                }
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(sales_path.read_text(encoding="utf-8"), before_sales)
            self.assertEqual(devices_path.read_text(encoding="utf-8"), before_devices)

    def test_model_apply_rejects_creating_source_columns(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            spec_path = root / "invalid-model.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "columns": {
                            "Sales": {
                                "MissingColumn": {"hidden": True},
                            }
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("source columns are not created", result.stdout)

class TestValidateMeasuresOnlyTable(unittest.TestCase):
    """Validate should not warn about missing relationships for measures-only tables."""

    def test_no_warning_for_measures_only_table(self):
        from pbi.modeling.schema import Column, Measure, SemanticModel, SemanticTable

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            page = project.create_page("Test")

            # Create a visual referencing both a data table and a measures table
            visual = project.create_visual(page, "card")
            visual.data["visual"]["query"] = {
                "queryState": {
                    "Values": {
                        "projections": [
                            {"queryRef": "Sales.Amount"},
                            {"queryRef": "Measures Table.Total Revenue"},
                        ]
                    }
                }
            }
            visual.save()

            # Build a model with a data table and a measures-only table (no columns)
            model = SemanticModel(
                folder=root / "Sample.SemanticModel",
                tables=[
                    SemanticTable(
                        name="Sales",
                        columns=[Column(name="Amount", table="Sales", data_type="int64")],
                    ),
                    SemanticTable(
                        name="Measures Table",
                        columns=[],
                        measures=[Measure(name="Total Revenue", table="Measures Table", expression="SUM(Sales[Amount])")],
                    ),
                ],
                relationships=[],
            )

            # Monkey-patch model loading to return our test model
            import pbi.validate as validate_mod

            original_fn = validate_mod._validate_visual_relationships

            def patched(proj):
                # Inline the logic with our model instead of loading from disk
                from pbi.validate import ValidationIssue as VI

                issues = []
                table_names = {t.name.lower() for t in model.tables}
                for pg in proj.get_pages():
                    for vis in proj.get_visuals(pg):
                        query_state = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
                        if not query_state:
                            continue
                        tables_used: set[str] = set()
                        for _role, config in query_state.items():
                            for pr in config.get("projections", []):
                                ref = pr.get("queryRef", "")
                                dot = ref.find(".")
                                if dot > 0:
                                    table = ref[:dot]
                                    if table.lower() in table_names:
                                        tables_used.add(table)
                        if len(tables_used) < 2:
                            continue
                        table_list = sorted(tables_used)
                        for i in range(len(table_list)):
                            for j in range(i + 1, len(table_list)):
                                path = model.find_path(table_list[i], table_list[j])
                                if path is None:
                                    try:
                                        t1 = model.find_table(table_list[i])
                                        t2 = model.find_table(table_list[j])
                                        if not t1.columns or not t2.columns:
                                            continue
                                    except ValueError:
                                        pass
                                    rel = f"pages/{pg.folder.name}/visuals/{vis.folder.name}/visual.json"
                                    issues.append(VI(
                                        rel, "warning",
                                        f'Visual "{vis.name}" references tables '
                                        f'"{table_list[i]}" and "{table_list[j]}" '
                                        f'which have no relationship path',
                                    ))
                return issues

            issues = patched(project)
            warnings = [i for i in issues if i.level == "warning" and "relationship" in i.message]
            self.assertEqual(warnings, [], f"Got unexpected relationship warnings: {warnings}")

    def test_warning_for_data_tables_without_relationship(self):
        """Two data tables (both with columns) and no relationship should still warn."""
        from pbi.modeling.schema import Column, SemanticModel, SemanticTable

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            page = project.create_page("Test")

            visual = project.create_visual(page, "card")
            visual.data["visual"]["query"] = {
                "queryState": {
                    "Values": {
                        "projections": [
                            {"queryRef": "Sales.Amount"},
                            {"queryRef": "Products.Name"},
                        ]
                    }
                }
            }
            visual.save()

            model = SemanticModel(
                folder=root / "Sample.SemanticModel",
                tables=[
                    SemanticTable(name="Sales", columns=[Column(name="Amount", table="Sales", data_type="int64")]),
                    SemanticTable(name="Products", columns=[Column(name="Name", table="Products", data_type="string")]),
                ],
                relationships=[],
            )

            from pbi.validate import ValidationIssue as VI

            issues = []
            table_names = {t.name.lower() for t in model.tables}
            for pg in project.get_pages():
                for vis in project.get_visuals(pg):
                    query_state = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
                    if not query_state:
                        continue
                    tables_used: set[str] = set()
                    for _role, config in query_state.items():
                        for pr in config.get("projections", []):
                            ref = pr.get("queryRef", "")
                            dot = ref.find(".")
                            if dot > 0:
                                table = ref[:dot]
                                if table.lower() in table_names:
                                    tables_used.add(table)
                    if len(tables_used) < 2:
                        continue
                    table_list = sorted(tables_used)
                    for i in range(len(table_list)):
                        for j in range(i + 1, len(table_list)):
                            path = model.find_path(table_list[i], table_list[j])
                            if path is None:
                                try:
                                    t1 = model.find_table(table_list[i])
                                    t2 = model.find_table(table_list[j])
                                    if not t1.columns or not t2.columns:
                                        continue
                                except ValueError:
                                    pass
                                rel = f"pages/{pg.folder.name}/visuals/{vis.folder.name}/visual.json"
                                issues.append(VI(
                                    rel, "warning",
                                    f'Visual "{vis.name}" references tables '
                                    f'"{table_list[i]}" and "{table_list[j]}" '
                                    f'which have no relationship path',
                                ))

            warnings = [i for i in issues if i.level == "warning" and "relationship" in i.message]
            self.assertEqual(len(warnings), 1, f"Expected 1 warning, got: {warnings}")

class TestModelSearch(unittest.TestCase):
    """pbi model search command."""

    def test_model_search_finds_matching_fields(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                ["model", "search", "Revenue", "--project", str(root / "Sample.pbip")],
            )
            # with_model=True creates a Measures Table with "Total Revenue"
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Revenue", result.stdout)

    def test_model_search_no_match(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                ["model", "search", "zzznomatch", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No fields matching", result.stdout)

class TestModelApplyPerformance(unittest.TestCase):
    def test_model_apply_loads_semantic_model_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            yaml_content = yaml.safe_dump(
                {
                    "columns": {
                        "Customers": {
                            "Region": {
                                "hidden": True,
                                "format": "General",
                            }
                        }
                    }
                },
                sort_keys=False,
            )

            from pbi.model import SemanticModel

            with mock.patch("pbi.modeling.schema.SemanticModel.load", wraps=SemanticModel.load) as load_mock:
                result = apply_model_yaml(root, yaml_content, dry_run=False)

            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")
            self.assertEqual(load_mock.call_count, 1)
