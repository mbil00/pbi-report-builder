from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from tests.cli_regressions_support import make_project, write_model_table


SALES_MODEL = """
table 'Sales'
    column 'Amount'
        dataType: int64
    column 'OrderDate'
        dataType: dateTime
    column 'Status'
        dataType: string
    measure 'Total Revenue' = SUM ( Sales[Amount] )
        formatString: #,0
"""


class ApplySchemaGroundingTests(unittest.TestCase):
    def _make_modeled_project(self, root: Path):
        project = make_project(root, with_model=True)
        write_model_table(root, "Sales.tmdl", SALES_MODEL)
        return project

    def test_apply_rejects_invalid_binding_field_when_model_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "card1",
                                    "type": "cardVisual",
                                    "bindings": {"Data": "Sales.Total Reveneu"},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertIn('Field "Total Reveneu" not found in table "Sales"', result.errors[0])

    def test_apply_rejects_invalid_sort_field_when_model_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "chart1",
                                    "type": "clusteredColumnChart",
                                    "bindings": {"Category": "Sales.OrderDate", "Y": "Sales.Total Revenue"},
                                    "sort": "Sales.OrderDat Ascending",
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any('Field "OrderDat" not found in table "Sales"' in err for err in result.errors))

    def test_apply_rejects_invalid_page_tooltip_shorthand_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Tip",
                            "tooltip": {"fields": ["Sales.OrderDat"]},
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any('Field "OrderDat" not found in table "Sales"' in err for err in result.errors))

    def test_apply_rejects_invalid_page_drillthrough_shorthand_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Drill",
                            "drillthrough": {"fields": ["Sales.OrderDat"]},
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any('Field "OrderDat" not found in table "Sales"' in err for err in result.errors))

    def test_apply_rejects_non_numeric_gradient_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "chart1",
                                    "type": "clusteredColumnChart",
                                    "conditionalFormatting": {
                                        "dataPoint.fill": {
                                            "mode": "gradient",
                                            "source": "Sales.Status",
                                            "min": {"color": "#ff0000", "value": 0},
                                            "max": {"color": "#00ff00", "value": 100},
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any("requires a numeric source" in err for err in result.errors))

    def test_apply_rejects_non_color_conditional_format_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "chart1",
                                    "type": "clusteredColumnChart",
                                    "conditionalFormatting": {
                                        "legend.show": {
                                            "mode": "measure",
                                            "source": "Sales.Total Revenue",
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any("not a color property" in err for err in result.errors))

    def test_apply_rejects_relative_filter_on_non_date_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "filters": [
                                {
                                    "field": "Sales.Status",
                                    "type": "relative",
                                    "operator": "InLast",
                                    "count": 7,
                                    "unit": "Days",
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(any("relative filters require a date/time column" in err.lower() for err in result.errors))
