from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.export import export_yaml
from pbi.filters import add_relative_date_filter
from pbi.project import Project


def _make_project(root: Path) -> Project:
    from pbi.schema_refs import REPORT_SCHEMA

    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}, "layoutOptimization": "None"}) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


class RelativeFilterApplyTests(unittest.TestCase):
    def test_apply_relative_date_filter_inlast(self) -> None:
        """InLast 30 Days relative date filter is applied without errors."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.OrderDate",
                                            "type": "relative",
                                            "operator": "InLast",
                                            "count": 30,
                                            "unit": "Days",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

            # Verify the filter JSON has type: RelativeDate
            page = project.find_page("Demo")
            visuals = project.get_visuals(page)
            visual = next(v for v in visuals if v.name == "card1")
            filters = visual.data.get("filterConfig", {}).get("filters", [])
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["type"], "RelativeDate")

    def test_apply_relative_time_filter(self) -> None:
        """InLast 15 Minutes relative time filter is applied without errors."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.EventTime",
                                            "type": "relative",
                                            "operator": "InLast",
                                            "count": 15,
                                            "unit": "Minutes",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

    def test_apply_relative_filter_invalid_operator(self) -> None:
        """An unrecognized operator produces an error containing 'operator'."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.OrderDate",
                                            "type": "relative",
                                            "operator": "BadOp",
                                            "count": 30,
                                            "unit": "Days",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors, "Expected at least one error")
            self.assertTrue(
                any("operator" in e for e in result.errors),
                f"Expected error about 'operator', got: {result.errors}",
            )

    def test_apply_relative_filter_invalid_unit(self) -> None:
        """An unrecognized unit produces an error containing 'unit'."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.OrderDate",
                                            "type": "relative",
                                            "operator": "InLast",
                                            "count": 2,
                                            "unit": "Fortnights",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors, "Expected at least one error")
            self.assertTrue(
                any("unit" in e for e in result.errors),
                f"Expected error about 'unit', got: {result.errors}",
            )

    def test_apply_relative_filter_inthis_rejects_time_units(self) -> None:
        """InThis is not valid for time units (Minutes/Hours) and produces an error."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.EventTime",
                                            "type": "relative",
                                            "operator": "InThis",
                                            "count": 1,
                                            "unit": "Minutes",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors, "Expected at least one error for InThis+Minutes")

    def test_apply_relative_filter_inthis_autocorrects_count(self) -> None:
        """InThis with count: 5 succeeds — count is auto-corrected to 1."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "type": "card",
                                    "name": "card1",
                                    "x": 0,
                                    "y": 0,
                                    "width": 200,
                                    "height": 100,
                                    "filters": [
                                        {
                                            "field": "Sales.OrderDate",
                                            "type": "relative",
                                            "operator": "InThis",
                                            "count": 5,
                                            "unit": "Months",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

    def test_apply_relative_filter_nonpositive_count(self) -> None:
        """count: 0 and count: -3 both produce errors containing 'count'."""
        for bad_count in (0, -3):
            with self.subTest(count=bad_count):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project = _make_project(root)
                    project.create_page("Demo")

                    spec = yaml.safe_dump(
                        {
                            "version": 1,
                            "pages": [
                                {
                                    "name": "Demo",
                                    "visuals": [
                                        {
                                            "type": "card",
                                            "name": "card1",
                                            "x": 0,
                                            "y": 0,
                                            "width": 200,
                                            "height": 100,
                                            "filters": [
                                                {
                                                    "field": "Sales.OrderDate",
                                                    "type": "relative",
                                                    "operator": "InLast",
                                                    "count": bad_count,
                                                    "unit": "Days",
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                        sort_keys=False,
                    )

                    result = apply_yaml(project, spec)

                    self.assertTrue(result.errors, f"Expected error for count={bad_count}")
                    self.assertTrue(
                        any("count" in e for e in result.errors),
                        f"Expected error about 'count' for count={bad_count}, got: {result.errors}",
                    )


class RelativeDateFilterExportTests(unittest.TestCase):
    def test_export_relative_date_produces_structured_yaml(self) -> None:
        """Exporting a visual with a relative date filter produces type: relative with structured fields."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart")
            visual.data["name"] = "chart1"
            add_relative_date_filter(
                visual.data,
                "Sales",
                "OrderDate",
                operator="InLast",
                time_units_count=30,
                time_unit_type="Days",
                include_today=False,
            )
            visual.save()

            exported = export_yaml(project)
            parsed = yaml.safe_load(exported)

            pages = parsed.get("pages", [])
            self.assertEqual(len(pages), 1)
            visuals = pages[0].get("visuals", [])
            self.assertEqual(len(visuals), 1)
            filters = visuals[0].get("filters", [])
            self.assertEqual(len(filters), 1)

            f = filters[0]
            self.assertEqual(f.get("type"), "relative", f"Expected type 'relative', got: {f.get('type')!r}")
            self.assertEqual(f.get("operator"), "InLast")
            self.assertEqual(f.get("count"), 30)
            self.assertEqual(f.get("unit"), "Days")
            self.assertNotIn("raw", f, "Structured relative filter should not have a 'raw' key")

    def test_roundtrip_relative_date_filter(self) -> None:
        """Relative date filter round-trips cleanly: export then apply produces no errors."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart")
            visual.data["name"] = "chart1"
            add_relative_date_filter(
                visual.data,
                "Sales",
                "OrderDate",
                operator="InLast",
                time_units_count=7,
                time_unit_type="Days",
                include_today=False,
            )
            visual.save()

            exported = export_yaml(project)
            parsed = yaml.safe_load(exported)

            # Verify includeToday is present and false in the export
            pages = parsed.get("pages", [])
            filters = pages[0].get("visuals", [])[0].get("filters", [])
            self.assertEqual(len(filters), 1)
            f = filters[0]
            self.assertIn("includeToday", f, "Expected includeToday key in exported filter")
            self.assertFalse(f["includeToday"], "Expected includeToday: false")

            # Re-apply to a fresh project
            with tempfile.TemporaryDirectory() as tmp2:
                root2 = Path(tmp2)
                project2 = _make_project(root2)
                result = apply_yaml(project2, exported)
                self.assertEqual(result.errors, [], f"Round-trip errors: {result.errors}")
                self.assertGreaterEqual(result.filters_added, 1)
