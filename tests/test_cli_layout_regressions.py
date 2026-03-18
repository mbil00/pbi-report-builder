from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.cli import app
from tests.cli_regressions_support import make_project


class TestCalcCommands(unittest.TestCase):
    """pbi calc row/grid layout calculators."""

    def test_calc_row_outputs_positions(self):
        runner = CliRunner()
        result = runner.invoke(app, ["calc", "row", "4", "--width", "1280", "--margin", "16", "--gap", "8"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("4 items", result.stdout)
        self.assertIn("#1", result.stdout)
        self.assertIn("#4", result.stdout)

    def test_calc_row_json(self):
        import json

        runner = CliRunner()
        result = runner.invoke(app, ["calc", "row", "3", "--width", "900", "--gap", "0", "--json"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        items = json.loads(result.stdout)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["x"], 0)
        self.assertEqual(items[0]["width"], 300)
        self.assertEqual(items[1]["x"], 300)
        self.assertEqual(items[2]["x"], 600)

    def test_calc_grid_outputs_positions(self):
        runner = CliRunner()
        result = runner.invoke(
            app, ["calc", "grid", "6", "--columns", "3", "--width", "900", "--gap", "0", "--item-height", "100", "--y", "50"]
        )
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("6 items", result.stdout)
        self.assertIn("3 cols", result.stdout)

    def test_calc_grid_json_positions(self):
        import json

        runner = CliRunner()
        result = runner.invoke(
            app, ["calc", "grid", "4", "--columns", "2", "--width", "400", "--gap", "0", "--item-height", "100", "--y", "0", "--json"]
        )
        self.assertEqual(result.exit_code, 0, result.stdout)
        items = json.loads(result.stdout)
        self.assertEqual(len(items), 4)
        # 2 cols x 2 rows, 200px each
        self.assertEqual(items[0]["x"], 0)
        self.assertEqual(items[0]["y"], 0)
        self.assertEqual(items[1]["x"], 200)
        self.assertEqual(items[1]["y"], 0)
        self.assertEqual(items[2]["x"], 0)
        self.assertEqual(items[2]["y"], 100)
        self.assertEqual(items[3]["x"], 200)
        self.assertEqual(items[3]["y"], 100)

class TestKpisShorthand(unittest.TestCase):
    """kpis: shorthand for cardVisual authoring."""

    def test_expand_kpis_builds_projections(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [
            {"measure": "Measures.Total", "referenceLabels": [
                {"measure": "Measures.Sub1"},
            ]},
            {"measure": "Measures.Rate"},
        ])

        projections = data["visual"]["query"]["queryState"]["Data"]["projections"]
        refs = [p["queryRef"] for p in projections]
        self.assertEqual(refs, ["Measures.Total", "Measures.Sub1", "Measures.Rate"])

    def test_expand_kpis_writes_per_measure_value_objects(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [
            {"measure": "T.A", "displayUnits": 1, "bold": True},
            {"measure": "T.B", "fontSize": 28},
        ])

        value_entries = data["visual"]["objects"]["value"]
        self.assertEqual(len(value_entries), 2)

        # First KPI
        self.assertEqual(value_entries[0]["selector"]["metadata"], "T.A")
        self.assertIn("labelDisplayUnits", value_entries[0]["properties"])
        self.assertIn("bold", value_entries[0]["properties"])

        # Second KPI
        self.assertEqual(value_entries[1]["selector"]["metadata"], "T.B")
        self.assertIn("fontSize", value_entries[1]["properties"])

    def test_expand_kpis_writes_accent_bar_per_kpi(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A", "accentColor": "#1A6B7D"}],
            accent_bar={"show": True, "position": "Top", "width": 5},
        )

        ab_entries = data["visual"]["objects"]["accentBar"]
        # Global entry + per-KPI entry
        self.assertEqual(len(ab_entries), 2)
        # Global uses default selector
        self.assertEqual(ab_entries[0]["selector"]["id"], "default")
        # Per-KPI uses metadata selector
        self.assertEqual(ab_entries[1]["selector"]["metadata"], "T.A")

    def test_expand_kpis_writes_tile_background(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [{"measure": "T.A", "tileBackground": "#F0F9FA"}])

        cca = data["visual"]["objects"]["cardCalloutArea"]
        self.assertEqual(len(cca), 1)
        self.assertEqual(cca[0]["selector"]["metadata"], "T.A")
        self.assertIn("backgroundFillColor", cca[0]["properties"])

    def test_expand_kpis_writes_reference_labels(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [{
            "measure": "T.Main",
            "referenceLabels": [
                {"measure": "T.Sub", "title": "Subtitle", "displayUnits": 1000},
            ],
        }])

        # Binding entry
        rl = data["visual"]["objects"]["referenceLabel"]
        self.assertEqual(len(rl), 1)
        sel = rl[0]["selector"]
        self.assertEqual(sel["metadata"], "T.Main")
        self.assertEqual(sel["id"], "field-kpi-0-ref-0")
        self.assertEqual(sel["order"], 0)
        # Value contains measure expression
        val_expr = rl[0]["properties"]["value"]["expr"]
        self.assertIn("Measure", val_expr)
        self.assertEqual(val_expr["Measure"]["Property"], "Sub")

        # Title entry
        rlt = data["visual"]["objects"]["referenceLabelTitle"]
        self.assertEqual(len(rlt), 1)
        self.assertEqual(rlt[0]["selector"]["id"], "field-kpi-0-ref-0")
        self.assertIn("titleText", rlt[0]["properties"])

        # Value formatting entry
        rlv = data["visual"]["objects"]["referenceLabelValue"]
        self.assertEqual(len(rlv), 1)
        self.assertIn("valueDisplayUnits", rlv[0]["properties"])

    def test_expand_kpis_writes_layout(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A"}],
            layout={"columns": 3, "calloutSize": 35, "alignment": "middle", "dividers": True},
        )

        layout_entries = data["visual"]["objects"]["layout"]
        self.assertEqual(len(layout_entries), 1)
        props = layout_entries[0]["properties"]
        self.assertIn("columnCount", props)
        self.assertIn("calloutSize", props)

        divider_entries = data["visual"]["objects"]["divider"]
        self.assertEqual(len(divider_entries), 1)

    def test_expand_kpis_writes_reference_label_layout(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A"}],
            ref_label_layout={"position": "right", "arrangement": "rows"},
        )

        rll = data["visual"]["objects"]["referenceLabelLayout"]
        self.assertEqual(len(rll), 1)
        self.assertEqual(rll[0]["selector"]["id"], "default")
        self.assertIn("position", rll[0]["properties"])
        self.assertIn("arrangement", rll[0]["properties"])

    def test_apply_yaml_kpis_shorthand(self):
        """End-to-end: YAML with kpis: block creates full cardVisual."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Dashboard")

            yaml_content = yaml.safe_dump({
                "version": 1,
                "pages": [{
                    "name": "Dashboard",
                    "visuals": [{
                        "name": "healthCard",
                        "type": "cardVisual",
                        "position": "16, 81",
                        "size": "1260 x 280",
                        "layout": {
                            "columns": 3,
                            "calloutSize": 35,
                            "alignment": "middle",
                            "dividers": True,
                        },
                        "accentBar": {
                            "show": True,
                            "position": "Top",
                            "width": 5,
                        },
                        "kpis": [
                            {
                                "measure": "Measures Table.Total Devices",
                                "displayUnits": 1,
                                "accentColor": "#1A6B7D",
                                "tileBackground": "#F0F9FA",
                                "referenceLabels": [{
                                    "measure": "Measures Table.Managed Devices",
                                    "title": "Managed",
                                    "displayUnits": 1,
                                }],
                            },
                            {
                                "measure": "Measures Table.Compliance Rate",
                                "accentColor": "#2B7A4B",
                            },
                        ],
                        "referenceLabelLayout": {
                            "position": "right",
                            "arrangement": "rows",
                        },
                    }],
                }],
            })

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertEqual(result.errors, [], f"Errors: {result.errors}")

            page = project.find_page("Dashboard")
            vis = next(v for v in project.get_visuals(page) if v.data.get("name") == "healthCard")

            # Verify projections
            projections = vis.data["visual"]["query"]["queryState"]["Data"]["projections"]
            refs = [p["queryRef"] for p in projections]
            self.assertIn("Measures Table.Total Devices", refs)
            self.assertIn("Measures Table.Managed Devices", refs)
            self.assertIn("Measures Table.Compliance Rate", refs)

            # Verify objects were created
            objects = vis.data["visual"]["objects"]
            self.assertIn("layout", objects)
            self.assertIn("accentBar", objects)
            self.assertIn("value", objects)
            self.assertIn("referenceLabel", objects)
            self.assertIn("referenceLabelTitle", objects)
            self.assertIn("referenceLabelLayout", objects)
