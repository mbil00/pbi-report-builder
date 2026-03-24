from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

_BUNDLE_PATH = Path(__file__).resolve().parents[1] / "schema-analysis" / "output" / "DESKTOP.MIN.JS"


@unittest.skipUnless(_BUNDLE_PATH.exists(), "PBI Desktop bundle not available (schema-analysis/output/DESKTOP.MIN.JS)")
class VisualCapabilityExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmp.name)
        result = subprocess.run(
            [
                "node",
                "scripts/extract_visual_capabilities.js",
                "--out-dir",
                str(cls.out_dir),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
        )
        cls.stdout = result.stdout
        cls.summary = json.loads((cls.out_dir / "visual-capabilities.summary.json").read_text(encoding="utf-8"))
        cls.full = json.loads((cls.out_dir / "visual-capabilities.full.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_extractor_reports_expected_coverage(self) -> None:
        self.assertIn("Extracted", self.stdout)
        meta = self.summary["meta"]
        self.assertGreaterEqual(meta["visualCount"], 50)
        self.assertGreater(meta["totalObjectDefinitions"], 300)
        self.assertGreater(meta["totalPropertyDefinitions"], 2000)
        self.assertIsInstance(meta["registryModuleId"], int)
        self.assertIn(meta["registryDiscovery"], {"source-scan", "export-scan"})
        self.assertTrue(meta["localizationOverrideModuleIds"])

    def test_line_chart_contains_secondary_axis_and_small_multiples(self) -> None:
        line_chart = self.full["visuals"]["lineChart"]
        self.assertEqual(
            line_chart["dataRoleNames"],
            ["Category", "Series", "Y", "Y2", "Rows", "Tooltips"],
        )
        self.assertIn("categoryAxis", line_chart["capabilities"]["objects"])
        self.assertIn(
            "labelPrecision",
            line_chart["capabilities"]["objects"]["categoryAxis"]["properties"],
        )

    def test_card_visual_has_large_object_surface(self) -> None:
        card_visual = self.summary["visuals"]["cardVisual"]
        self.assertGreaterEqual(card_visual["objectCount"], 30)
        self.assertIn("referenceLabelValue", card_visual["objectNames"])
        self.assertIn("fillCustom", card_visual["objectNames"])

    def test_slicer_and_shape_map_roles_match_desktop_registry(self) -> None:
        slicer = self.full["visuals"]["slicer"]
        self.assertEqual(slicer["dataRoleNames"], ["Values"])
        self.assertIn("selection", slicer["capabilities"]["objects"])

        shape_map = self.full["visuals"]["shapeMap"]
        self.assertEqual(shape_map["dataRoleNames"], ["Category", "Series", "Value", "Tooltips"])
        self.assertIn("defaultColors", shape_map["capabilities"]["objects"])


if __name__ == "__main__":
    unittest.main()
