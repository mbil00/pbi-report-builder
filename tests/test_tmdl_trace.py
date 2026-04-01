from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from pbi.model import build_tmdl_trace, format_tmdl_trace_report


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def _make_model(root: Path) -> Path:
    definition = root / "Sample.SemanticModel" / "definition"
    _write(
        definition / "model.tmdl",
        """
        model Model
            annotation __PBI_TimeIntelligenceEnabled = "1"
            annotation PBI_ProTooling = ["DevMode"]
        """,
    )
    _write(
        definition / "tables" / "Sales.tmdl",
        """
        table Sales
            column Region
                dataType: string
            column Year
                dataType: int64
            calculatedColumn Bucket = IF ( Sales[Revenue] > 100, "High", "Low" )
                dataType: string
            measure Revenue = SUM ( Sales[Amount] )
                formatString: "$#,0"
            hierarchy Calendar
                level Year
                    column: Year
            partition Sales = m
                mode: import
                source =
                    let
                        Source = 1
                    in
                        Source
        """,
    )
    _write(
        definition / "tables" / "Customers.tmdl",
        """
        table Customers
            column CustomerID
                dataType: int64
        """,
    )
    _write(
        definition / "relationships.tmdl",
        """
        relationship rel-1
            fromColumn: Sales.Region
            toColumn: Customers.CustomerID
            isActive: true
        """,
    )
    _write(
        definition / "roles" / "Finance Readers.tmdl",
        """
        role 'Finance Readers'
            modelPermission: read
            tablePermission Sales = Sales[Region] = "EU"
            member finance@example.com = user
                identityProvider = aad
        """,
    )
    _write(
        definition / "perspectives" / "Exec View.tmdl",
        """
        perspective 'Exec View'
            perspectiveTable Sales
                perspectiveColumn Region
                perspectiveMeasure Revenue
                perspectiveHierarchy Calendar
        """,
    )
    return root


class TmdlTraceTests(unittest.TestCase):
    def test_build_tmdl_trace_indexes_model_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_model(Path(tmp))
            trace = build_tmdl_trace(root)

            meta = trace["meta"]
            self.assertEqual(meta["tableCount"], 2)
            self.assertEqual(meta["relationshipCount"], 1)
            self.assertEqual(meta["roleCount"], 1)
            self.assertEqual(meta["perspectiveCount"], 1)
            self.assertEqual(meta["annotationCount"], 2)

            revenue = trace["refs"]["measure:Sales.Revenue"]
            self.assertTrue(revenue["path"].endswith("Sales.tmdl"))
            self.assertIn("measure Revenue", revenue["snippet"])
            self.assertEqual(revenue["table"], "Sales")

            relationship = trace["refs"]["relationship:Sales.Region->Customers.CustomerID"]
            self.assertEqual(relationship["kind"], "relationship")
            self.assertEqual(relationship["fromTable"], "Sales")
            self.assertEqual(relationship["toTable"], "Customers")
            self.assertIn("fromColumn: Sales.Region", relationship["snippet"])

            annotation = trace["refs"]["annotation:__PBI_TimeIntelligenceEnabled"]
            self.assertIn("__PBI_TimeIntelligenceEnabled", annotation["snippet"])

    def test_format_report_includes_location_and_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_model(Path(tmp))
            trace = build_tmdl_trace(root)
            report = format_tmdl_trace_report(trace, "measure:Sales.Revenue")
            self.assertIn("Ref: measure:Sales.Revenue", report)
            self.assertIn("Kind: measure", report)
            self.assertIn("Path:", report)
            self.assertIn("measure Revenue = SUM", report)

    def test_scripts_extract_and_inspect_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_model(Path(tmp))
            out_path = root / "tmdl.trace.json"

            subprocess.run(
                [
                    sys.executable,
                    "scripts/extract_tmdl_trace.py",
                    "--project-root",
                    str(root),
                    "--out",
                    str(out_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )

            manifest = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("measure:Sales.Revenue", manifest["refs"])

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/inspect_tmdl_trace.py",
                    "--project-root",
                    str(root),
                    "--ref",
                    "role:Finance Readers",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("Ref: role:Finance Readers", result.stdout)
            self.assertIn("role 'Finance Readers'", result.stdout)


if __name__ == "__main__":
    unittest.main()
