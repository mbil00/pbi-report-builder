from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pbi.apply import apply_yaml
from pbi.export import export_yaml
from pbi.filters import add_topn_filter
from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA


class YamlRoundTripTests(unittest.TestCase):
    def _make_project(self, root: Path) -> Project:
        pbip = root / "Sample.pbip"
        report = root / "Sample.Report"
        definition = report / "definition"
        definition.mkdir(parents=True)
        pbip.write_text(
            json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
            encoding="utf-8",
        )
        (definition / "report.json").write_text(
            json.dumps(
                {
                    "$schema": REPORT_SCHEMA,
                    "themeCollection": {},
                    "layoutOptimization": "None",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return Project.find(pbip)

    def test_round_trip_preserves_float_geometry_and_unnamed_visual_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            original = project.create_visual(
                page,
                "textSlicer",
                x=9.5,
                y=20.25,
                width=300.75,
                height=100.5,
            )

            spec = export_yaml(project, page_filter="Demo")
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            visuals = project.get_visuals(page)
            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0].folder.name, original.folder.name)
            self.assertEqual(visuals[0].position["x"], 9.5)
            self.assertEqual(visuals[0].position["width"], 300.75)

    def test_round_trip_preserves_topn_filters_via_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            add_topn_filter(
                page.data,
                "Customers",
                "Region",
                n=5,
                order_entity="Sales",
                order_prop="Total Revenue",
            )
            page.save()
            spec = export_yaml(source, page_filter="Demo")

            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.warnings, [])

            page = target.find_page("Demo")
            filters = page.data["filterConfig"]["filters"]
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["type"], "TopN")

    def test_round_trip_preserves_minimal_card_payload_via_raw_visual_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "cardVisual", x=10, y=20, width=300, height=100)
            visual.data["name"] = "card1"
            visual.save()
            spec = export_yaml(source, page_filter="Demo")

            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "card1")
            self.assertEqual(visual.data["visual"]["objects"], {})
            self.assertNotIn("visualContainerObjects", visual.data["visual"])

    def test_apply_include_filter_keeps_include_type(self) -> None:
        spec = """\
version: 1
pages:
- name: Demo
  filters:
  - field: Product.Category
    type: Include
    values: [Bikes]
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            filters = page.data["filterConfig"]["filters"]
            self.assertEqual(filters[0]["type"], "Include")
            self.assertEqual(filters[0]["howCreated"], "Include")


if __name__ == "__main__":
    unittest.main()
