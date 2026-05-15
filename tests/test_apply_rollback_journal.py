from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pbi.apply.rollback import RollbackJournal


class RollbackJournalTests(unittest.TestCase):
    def test_existing_file_write_rollback_restores_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "definition" / "report.json"
            path.parent.mkdir()
            path.write_bytes(b"before")
            journal = RollbackJournal(root=root)

            journal.capture_file(path)
            path.write_bytes(b"after")
            journal.restore()

            self.assertEqual(path.read_bytes(), b"before")

    def test_new_file_write_rollback_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "definition" / "new.json"
            path.parent.mkdir()
            journal = RollbackJournal(root=root)

            journal.capture_file(path)
            path.write_bytes(b"created")
            journal.restore()

            self.assertFalse(path.exists())

    def test_created_directory_rollback_removes_new_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "definition" / "pages" / "newpage"
            journal = RollbackJournal(root=root)

            journal.capture_created_dir(folder)
            (folder / "visuals").mkdir(parents=True)
            (folder / "page.json").write_bytes(b"{}")
            journal.restore()

            self.assertFalse(folder.exists())

    def test_created_directory_rollback_keeps_preexisting_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "definition" / "pages"
            folder.mkdir(parents=True)
            journal = RollbackJournal(root=root)

            journal.capture_created_dir(folder)
            (folder / "new.json").write_bytes(b"{}")
            journal.restore()

            self.assertTrue(folder.exists())
            self.assertTrue((folder / "new.json").exists())

    def test_deleted_tree_rollback_restores_nested_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "definition" / "pages" / "p1" / "visuals" / "v1"
            nested = folder / "sub" / "resource.bin"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"resource")
            (folder / "visual.json").write_bytes(b"visual")
            journal = RollbackJournal(root=root)

            journal.capture_deleted_tree(folder)
            for path in sorted(folder.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            folder.rmdir()
            journal.restore()

            self.assertEqual((folder / "visual.json").read_bytes(), b"visual")
            self.assertEqual(nested.read_bytes(), b"resource")

    def test_directory_children_capture_removes_unknown_new_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "definition" / "pages"
            existing = parent / "existing"
            existing.mkdir(parents=True)
            (existing / "page.json").write_bytes(b"existing")
            journal = RollbackJournal(root=root)

            journal.capture_directory_children(parent)
            new_child = parent / "generated"
            new_child.mkdir()
            (new_child / "page.json").write_bytes(b"new")
            journal.restore()

            self.assertTrue(existing.exists())
            self.assertFalse(new_child.exists())

    def test_capture_buffered_changes_dedupes_dirty_file_under_deleted_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "definition" / "pages" / "p1" / "visuals" / "v1"
            visual_json = folder / "visual.json"
            folder.mkdir(parents=True)
            visual_json.write_bytes(b"before")

            journal = RollbackJournal.capture_buffered_changes(
                root=root,
                dirty_json={visual_json: {"name": "changed"}},
                created_dirs=set(),
                deleted_dirs={folder},
            )
            # Simulate buffered flush: delete wins, dirty file under deleted tree is skipped.
            for path in sorted(folder.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            folder.rmdir()
            journal.restore()

            self.assertEqual(visual_json.read_bytes(), b"before")


if __name__ == "__main__":
    unittest.main()
