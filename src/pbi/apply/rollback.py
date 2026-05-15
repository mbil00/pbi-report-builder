"""Touched-path rollback journal for apply sessions.

The journal records pre-change file bytes and directory trees for paths an
apply commit is about to mutate. It is intentionally narrower than a full
report snapshot: rollback work is proportional to touched paths.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class _FileBeforeImage:
    existed: bool
    content: bytes | None = None


@dataclass
class _DeletedTreeBeforeImage:
    existed: bool
    directories: set[Path] = field(default_factory=set)
    files: dict[Path, bytes] = field(default_factory=dict)


@dataclass
class RollbackJournal:
    """Before-image journal for restoring touched filesystem paths."""

    root: Path
    files: dict[Path, _FileBeforeImage] = field(default_factory=dict)
    created_dirs: dict[Path, bool] = field(default_factory=dict)
    deleted_trees: dict[Path, _DeletedTreeBeforeImage] = field(default_factory=dict)

    @classmethod
    def capture_buffered_changes(
        cls,
        *,
        root: Path,
        dirty_json: dict[Path, dict[str, Any]],
        created_dirs: set[Path],
        deleted_dirs: set[Path],
    ) -> RollbackJournal:
        """Capture before-images for a buffered PBIR flush."""
        journal = cls(root=root)
        for folder in sorted(deleted_dirs, key=lambda path: len(path.parts)):
            journal.capture_deleted_tree(folder)

        deleted_prefixes = tuple(_path_prefix(path) for path in deleted_dirs)
        for folder in sorted(created_dirs, key=lambda path: len(path.parts)):
            if _is_under_any_prefix(folder, deleted_prefixes):
                continue
            journal.capture_created_dir(folder)

        for path in sorted(dirty_json):
            if _is_under_any_prefix(path, deleted_prefixes):
                continue
            journal.capture_file(path)
        return journal

    def capture_file(self, path: Path) -> None:
        """Record the current bytes for a file that may be written."""
        path = self._normalize(path)
        if path in self.files:
            return
        if path.exists():
            self.files[path] = _FileBeforeImage(True, path.read_bytes())
        else:
            self.files[path] = _FileBeforeImage(False, None)

    def capture_created_dir(self, path: Path) -> None:
        """Record whether a directory existed before it may be created.

        Parent directories created implicitly by ``mkdir(parents=True)`` are
        journaled too, up to but not including the journal root, so rollback
        can remove now-empty ancestor directories and match whole-tree restore
        semantics.
        """
        path = self._normalize(path)
        self.created_dirs.setdefault(path, path.exists())
        current = path.parent
        while current != self.root and current != current.parent:
            if not current.exists():
                self.created_dirs.setdefault(current, False)
            current = current.parent

    def record_created_dir(self, path: Path) -> None:
        """Record that a directory was newly created by the protected operation."""
        path = self._normalize(path)
        self.created_dirs[path] = False

    def capture_deleted_tree(self, path: Path) -> None:
        """Record a directory subtree before it may be deleted."""
        path = self._normalize(path)
        if path in self.deleted_trees:
            return
        if not path.exists():
            self.deleted_trees[path] = _DeletedTreeBeforeImage(False)
            return

        directories = {path}
        files: dict[Path, bytes] = {}
        for child in path.rglob("*"):
            if child.is_dir():
                directories.add(child)
            elif child.is_file():
                files[child] = child.read_bytes()
        self.deleted_trees[path] = _DeletedTreeBeforeImage(
            True,
            directories=directories,
            files=files,
        )

    def restore(self) -> None:
        """Restore captured paths to their pre-change state."""
        self._restore_deleted_trees()
        self._restore_existing_files()
        self._remove_new_files()
        self._remove_new_dirs()

    def _restore_deleted_trees(self) -> None:
        for root, image in sorted(
            self.deleted_trees.items(), key=lambda item: len(item[0].parts)
        ):
            if not image.existed:
                if root.exists():
                    shutil.rmtree(root)
                continue
            if root.exists():
                shutil.rmtree(root)
            for folder in sorted(image.directories, key=lambda path: len(path.parts)):
                folder.mkdir(parents=True, exist_ok=True)
            for path, content in sorted(image.files.items()):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

    def _restore_existing_files(self) -> None:
        deleted_prefixes = tuple(_path_prefix(path) for path in self.deleted_trees)
        for path, image in sorted(self.files.items()):
            if not image.existed or _is_under_any_prefix(path, deleted_prefixes):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image.content or b"")

    def _remove_new_files(self) -> None:
        deleted_prefixes = tuple(_path_prefix(path) for path in self.deleted_trees)
        for path, image in sorted(self.files.items(), reverse=True):
            if image.existed or _is_under_any_prefix(path, deleted_prefixes):
                continue
            if path.exists():
                path.unlink()

    def _remove_new_dirs(self) -> None:
        for path, existed in sorted(
            self.created_dirs.items(), key=lambda item: len(item[0].parts), reverse=True
        ):
            if existed or not path.exists():
                continue
            shutil.rmtree(path)

    def _normalize(self, path: Path) -> Path:
        return Path(path)


def _path_prefix(path: Path) -> str:
    return f"{path.as_posix().rstrip('/')}/"


def _is_under_any_prefix(path: Path, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return False
    path_string = f"{path.as_posix().rstrip('/')}/"
    return any(path_string.startswith(prefix) for prefix in prefixes)
