"""Tests for the report-04 Desktop-shapes fixture.

The build inputs (CSVs, theme, image, checklist) are generated and must stay
byte-stable. The Desktop-built PBIP itself is added later by hand; the tests
for it skip until `04-desktop-shapes.pbip` exists.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import ModuleType

from pbi.model import SemanticModel
from pbi.project import Project


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "real-report-fixtures"
SHAPES_DIR = FIXTURE_ROOT / "report-04-desktop-shapes"
SHAPES_DATA = SHAPES_DIR / "data"
SHAPES_PBIP = SHAPES_DIR / "04-desktop-shapes.pbip"

EXPECTED_PAGES = [
    "Overview",
    "Task Board",
    "Filter Lab",
    "Chart Gallery",
    "Project Detail",
    "Person Tooltip",
    "QA Hidden",
]


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_fixture_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DesktopShapesInputsTests(unittest.TestCase):
    """The committed build inputs match what the generators produce."""

    def test_dataset_regenerates_byte_identical(self) -> None:
        datasets = _load_script("generate_fixture_datasets")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = datasets.generate_desktop_shapes(out)
            generated = sorted(path.name for path in out.iterdir())
            committed = sorted(path.name for path in SHAPES_DATA.iterdir())
            self.assertEqual(generated, committed)
            for name in generated:
                self.assertEqual(
                    (out / name).read_bytes(),
                    (SHAPES_DATA / name).read_bytes(),
                    f"{name} differs; rerun scripts/generate_fixture_datasets.py",
                )
        self.assertEqual(manifest["Task_rows"], 600)

    def test_checklist_regenerates_identical(self) -> None:
        checklists = _load_script("generate_fixture_build_checklists")
        rendered = checklists.build_checklist("report-04-desktop-shapes", SHAPES_DATA)
        committed = (SHAPES_DIR / "BUILD-CHECKLIST.md").read_text(encoding="utf-8")
        self.assertEqual(rendered, committed, "rerun scripts/generate_fixture_build_checklists.py")
        self.assertNotIn("@@", rendered)
        for page in EXPECTED_PAGES:
            self.assertIn(f"`{page}`", rendered)

    def test_resource_inputs_have_spaces_and_are_valid(self) -> None:
        theme = SHAPES_DATA / "Desktop Shapes Theme.json"
        self.assertIn('"name": "Desktop Shapes Theme"', theme.read_text(encoding="utf-8"))
        self.assertNotIn("textClasses", theme.read_text(encoding="utf-8"))

        png = (SHAPES_DATA / "Team Logo.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        idat_len = struct.unpack(">I", png[33:37])[0]
        self.assertEqual(png[37:41], b"IDAT")
        pixels = zlib.decompress(png[41:41 + idat_len])
        self.assertEqual(len(pixels), height * (1 + width * 3))


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopShapesFixtureTests(unittest.TestCase):
    """Activates once the Desktop-built PBIP is committed."""

    def test_pages_match_spec(self) -> None:
        project = Project.find(SHAPES_PBIP)
        self.assertEqual([page.display_name for page in project.get_pages()], EXPECTED_PAGES)

    def test_model_has_special_character_tables(self) -> None:
        project = Project.find(SHAPES_PBIP)
        names = {table.name for table in SemanticModel.load(project.root).tables}
        # Q/A Notes and Owner's Info have documented fallbacks in BUILD-NOTES.md.
        for expected in ("Rates (EUR)", "Time & Expenses", "Measures Table", "Portfolio Target"):
            self.assertIn(expected, names)
        self.assertTrue({"Q/A Notes", "QA Notes"} & names)
        self.assertTrue({"Owner's Info", "Owners Info"} & names)


if __name__ == "__main__":
    unittest.main()
