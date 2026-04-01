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
        cls.trace = json.loads((cls.out_dir / "visual-capabilities.trace.json").read_text(encoding="utf-8"))
        cls.analysis = json.loads((cls.out_dir / "visual-capabilities.analysis.json").read_text(encoding="utf-8"))

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

    def test_trace_manifest_records_provider_provenance(self) -> None:
        meta = self.trace["meta"]
        self.assertEqual(meta["visualCount"], self.summary["meta"]["visualCount"])
        self.assertEqual(meta["registryModuleId"], self.summary["meta"]["registryModuleId"])
        self.assertTrue(meta["registryLocalSymbol"])

        card_visual = self.trace["visuals"]["cardVisual"]
        self.assertIsInstance(card_visual["registryEntry"]["expression"], str)
        self.assertTrue(card_visual["registryEntry"]["expression"])
        self.assertEqual(card_visual["provider"]["kind"], "moduleExport")
        self.assertIsInstance(card_visual["provider"]["moduleId"], int)
        self.assertTrue(card_visual["provider"]["exportName"])
        self.assertTrue(card_visual["provider"]["localSymbol"])
        self.assertIn("objects:", card_visual["provider"]["snippet"])
        self.assertIn("dataRoles", card_visual["provider"]["snippet"])
        shared_refs = {item["rawRef"]: item for item in card_visual["provider"]["importedReferences"]}
        self.assertIn("l.ZX.accentBar", shared_refs)
        self.assertEqual(shared_refs["l.ZX.accentBar"]["moduleId"], 697265)

    def test_analysis_manifest_normalizes_roles_properties_and_mappings(self) -> None:
        meta = self.analysis["meta"]
        self.assertEqual(meta["visualCount"], self.summary["meta"]["visualCount"])

        line_chart = self.analysis["visuals"]["lineChart"]
        role_names = [role["name"] for role in line_chart["dataRoles"]]
        self.assertEqual(role_names, ["Category", "Series", "Y", "Y2", "Rows", "Tooltips"])
        y_role = next(role for role in line_chart["dataRoles"] if role["name"] == "Y")
        self.assertTrue(y_role["requiredTypes"])
        self.assertEqual(y_role["requiredTypes"][0]["kind"], "numeric")

        accent_bar = self.analysis["visuals"]["cardVisual"]["objects"]["accentBar"]
        self.assertGreaterEqual(accent_bar["propertyCount"], 1)
        self.assertEqual(accent_bar["properties"]["show"]["type"]["kind"], "bool")

        mappings = line_chart["dataViewMappings"]
        self.assertGreaterEqual(len(mappings), 1)
        self.assertIn("matrix", mappings[0]["shapeKinds"])
        self.assertIn("Y", mappings[0]["roleNames"])
        self.assertTrue(mappings[0]["dataReductionAlgorithms"])
        self.assertIn("supportsOnObjectFormatting", line_chart["behavior"])

    def test_slicer_and_shape_map_roles_match_desktop_registry(self) -> None:
        slicer = self.full["visuals"]["slicer"]
        self.assertEqual(slicer["dataRoleNames"], ["Values"])
        self.assertIn("selection", slicer["capabilities"]["objects"])

        shape_map = self.full["visuals"]["shapeMap"]
        self.assertEqual(shape_map["dataRoleNames"], ["Category", "Series", "Value", "Tooltips"])
        self.assertIn("defaultColors", shape_map["capabilities"]["objects"])

    def test_trace_inspector_cli_outputs_card_visual_provenance(self) -> None:
        result = subprocess.run(
            [
                "node",
                "scripts/inspect_visual_capability_trace.js",
                "--bundle",
                str(_BUNDLE_PATH),
                "--visual",
                "cardVisual",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Visual: cardVisual", result.stdout)
        self.assertIn("Provider:", result.stdout)
        self.assertIn("objects:", result.stdout)
        self.assertIn("Imported references:", result.stdout)


if __name__ == "__main__":
    unittest.main()
