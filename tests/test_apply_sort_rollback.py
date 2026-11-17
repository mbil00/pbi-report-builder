"""Apply sort writes go through the session's rollback journal (#70).

Runs against the report-04 Desktop-saved fixture, whose Task Board visuals carry
Desktop's own ``sortDefinition`` shapes: ``2583acebb02c0007195a`` has
``isDefaultSort: true`` and ``518a30c4007b6397ed6d`` has no ``isDefaultSort``.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.project import Project, Visual
from pbi.visual_queries import set_sort
from tests.support import SHAPES_DIR


SHAPES_PBIP = SHAPES_DIR / "04-desktop-shapes.pbip"

SLICER_ID = "2583acebb02c0007195a"  # Date.Date Ascending, isDefaultSort: true
TABLE_ID = "518a30c4007b6397ed6d"  # Total Hours Descending, no isDefaultSort


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop PBIP not present")
class ApplySortRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "proj"
        shutil.copytree(SHAPES_DIR, self.root)
        self.project = Project.find(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _apply(self, visuals: list[dict]) -> object:
        spec = {"version": 1, "pages": [{"name": "Task Board", "visuals": visuals}]}
        return apply_yaml(self.project, yaml.safe_dump(spec, sort_keys=False))

    def test_failed_apply_restores_sorted_visuals_byte_identical(self) -> None:
        before = _snapshot(self.root)

        result = self._apply([
            # A different sort, so the visual really changes before the failure.
            {"id": TABLE_ID, "type": "tableEx", "sort": "Person.PersonName Ascending"},
            {"id": SLICER_ID, "type": "slicer", "sort": "Date.Date Ascending"},
            # A later visual fails, which rolls the whole apply back.
            {"name": "broken", "type": "tableEx", "bindings": {"Values": ["Nope.Missing"]}},
        ])

        self.assertTrue(result.rolled_back)
        self.assertTrue(result.errors)
        self.assertEqual(_snapshot(self.root), before)

    def test_reapplying_the_existing_sort_leaves_the_file_untouched(self) -> None:
        paths = {
            visual_id: next(self.root.rglob(f"visuals/{visual_id}/visual.json"))
            for visual_id in (SLICER_ID, TABLE_ID)
        }
        before = {visual_id: path.read_bytes() for visual_id, path in paths.items()}

        result = self._apply([
            {"id": SLICER_ID, "type": "slicer", "sort": "Date.Date Ascending"},
            {
                "id": TABLE_ID,
                "type": "tableEx",
                "sort": "Measures Table.Total Hours (measure) Descending",
            },
        ])

        self.assertEqual(result.errors, [])
        for visual_id, path in paths.items():
            self.assertEqual(path.read_bytes(), before[visual_id], visual_id)


class SetSortTests(unittest.TestCase):
    def _visual(self, sort_definition: dict | None) -> Visual:
        query: dict = {}
        if sort_definition is not None:
            query["sortDefinition"] = sort_definition
        return Visual(Path("unused"), {"visual": {"visualType": "tableEx", "query": query}})

    @staticmethod
    def _entry(prop: str, direction: str) -> dict:
        return {
            "field": {"Column": {"Expression": {"SourceRef": {"Entity": "Date"}}, "Property": prop}},
            "direction": direction,
        }

    def test_same_sort_keeps_desktop_default_flag(self) -> None:
        existing = {"sort": [self._entry("Date", "Ascending")], "isDefaultSort": True}
        visual = self._visual(dict(existing))

        set_sort(visual, "Date", "Date", descending=False, save=False)

        self.assertEqual(visual.data["visual"]["query"]["sortDefinition"], existing)

    def test_different_sort_replaces_definition(self) -> None:
        visual = self._visual({"sort": [self._entry("Date", "Ascending")], "isDefaultSort": True})

        set_sort(visual, "Date", "Date", descending=True, save=False)

        self.assertEqual(
            visual.data["visual"]["query"]["sortDefinition"],
            {"sort": [self._entry("Date", "Descending")], "isDefaultSort": False},
        )


if __name__ == "__main__":
    unittest.main()
