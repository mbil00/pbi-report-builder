"""Trial apply: run ``apply`` on a throwaway copy and report what it would change.

``pbi diff`` uses this so its verdict comes from the apply engine itself: the
same resolution, validation and writers, run against a temporary copy of the
project. Whatever apply would reject shows up as errors, and whatever it would
write shows up as changed files, so ``diff`` and ``apply`` can't disagree.
"""

from __future__ import annotations

import filecmp
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.apply.engine import apply_yaml
from pbi.apply.state import ApplyResult
from pbi.project import Project

# Folders a project keeps beside the report and model that apply may read
# (styles, components, templates, saved themes, custom visual schemas).
_SIDECAR_PREFIX = ".pbi-"
# Desktop's per-user cache folder (it can hold a large ``cache.abf``); apply
# never reads it.
_IGNORED = shutil.ignore_patterns(".pbi")


@dataclass(frozen=True)
class FileChange:
    """One file apply would add, remove or rewrite (path relative to the project root)."""

    path: str
    kind: str  # "added", "removed" or "modified"
    details: list[str] = field(default_factory=list)


@dataclass
class TrialApply:
    """What a real apply of the same YAML would do."""

    result: ApplyResult
    changes: list[FileChange]

    @property
    def is_noop(self) -> bool:
        return not self.result.errors and not self.changes


def trial_apply(
    project: Project,
    yaml_content: str,
    *,
    page_filter: str | None = None,
) -> TrialApply:
    """Apply ``yaml_content`` to a temporary copy of ``project`` and compare the trees."""
    with tempfile.TemporaryDirectory(prefix="pbi-diff-") as tmp:
        copy_root = Path(tmp) / project.root.name
        for source in _copied_paths(project):
            target = copy_root / source.relative_to(project.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=_IGNORED)
            else:
                shutil.copy2(source, target)

        trial = Project.find(copy_root / project.pbip_file.name)
        result = apply_yaml(trial, yaml_content, page_filter=page_filter)
        changes: list[FileChange] = []
        for source in _copied_paths(project):
            rel = source.relative_to(project.root)
            changes.extend(_compare(source, copy_root / rel, rel))
    return TrialApply(result=result, changes=sorted(changes, key=lambda c: c.path))


def _copied_paths(project: Project) -> list[Path]:
    """The pieces of the project apply reads or writes."""
    paths = [project.pbip_file, project.report_folder]
    paths.extend(sorted(project.root.glob("*.SemanticModel")))
    paths.extend(
        sorted(
            child
            for child in project.root.iterdir()
            if child.is_dir() and child.name.startswith(_SIDECAR_PREFIX)
        )
    )
    return [path for path in paths if path.exists()]


def _compare(before: Path, after: Path, rel: Path) -> list[FileChange]:
    if before.is_file():
        return [] if _same_file(before, after) else [_modified(before, after, rel)]

    before_files = _files_under(before)
    after_files = _files_under(after) if after.is_dir() else set()
    changes = [
        FileChange((rel / name).as_posix(), "added")
        for name in sorted(after_files - before_files)
    ]
    changes.extend(
        FileChange((rel / name).as_posix(), "removed")
        for name in sorted(before_files - after_files)
    )
    for name in sorted(before_files & after_files):
        if not _same_file(before / name, after / name):
            changes.append(_modified(before / name, after / name, rel / name))
    return changes


def _files_under(root: Path) -> set[Path]:
    files: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != ".pbi"]
        base = Path(dirpath).relative_to(root)
        files.update(base / name for name in filenames)
    return files


def _same_file(before: Path, after: Path) -> bool:
    return after.is_file() and filecmp.cmp(before, after, shallow=False)


def _modified(before: Path, after: Path, rel: Path) -> FileChange:
    details: list[str] = []
    if before.suffix.lower() == ".json":
        try:
            old = json.loads(before.read_bytes().decode("utf-8-sig"))
            new = json.loads(after.read_bytes().decode("utf-8-sig"))
        except ValueError:
            pass
        else:
            json_changes(old, new, "", details)
            if not details:
                details.append("formatting only")
    return FileChange(rel.as_posix(), "modified", details)


def json_changes(old: Any, new: Any, path: str, out: list[str]) -> None:
    """Append one line per differing JSON path: values, types, keys and key order."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in old:
            if key not in new:
                out.append(f"{_join(path, key)}: removed")
        for key in new:
            if key not in old:
                out.append(f"{_join(path, key)}: added")
        common_old = [key for key in old if key in new]
        common_new = [key for key in new if key in old]
        if common_old != common_new:
            out.append(f"{path or '(root)'}: key order changed")
        for key in common_old:
            json_changes(old[key], new[key], _join(path, key), out)
        return
    if isinstance(old, list) and isinstance(new, list):
        for index, (old_item, new_item) in enumerate(zip(old, new)):
            json_changes(old_item, new_item, f"{path}[{index}]", out)
        for index in range(len(new), len(old)):
            out.append(f"{path}[{index}]: removed")
        for index in range(len(old), len(new)):
            out.append(f"{path}[{index}]: added")
        return
    if type(old) is not type(new) or old != new:
        out.append(f"{path or '(root)'}: {_short(old)} -> {_short(new)}")


def _join(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}" if path else key
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _short(value: Any, limit: int = 60) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."
