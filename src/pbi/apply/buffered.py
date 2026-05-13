"""Experimental buffered PBIR apply session.

This module is the secondary apply path used to grow toward a future
session/daemon architecture. The class intentionally starts as a skeleton: it
satisfies the same write-session protocol as the eager ``PbirApplySession`` so
parity tests can be added first, then staged operations can be implemented one
vertical slice at a time.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.apply.state import restore_definition_snapshot
from pbi.project import Page, Project, Visual, _read_json, _write_json
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA, VISUAL_CONTAINER_SCHEMA


_MISSING_MODEL = object()


class UnsupportedBufferedOperation(NotImplementedError):
    """Raised when the experimental buffered path reaches a future slice."""


@dataclass
class BufferedPbirApplySession:
    """Buffered PBIR apply session under active development.

    Lifecycle hooks are functional, but write methods deliberately raise until
    their vertical slice is implemented. This lets no-write/no-op parity tests
    establish the harness without accidentally falling back to eager writes.
    """

    project: Project
    dry_run: bool
    model: Any = _MISSING_MODEL
    dirty_pages: dict[Path, Page] = field(default_factory=dict)
    dirty_visuals: dict[Path, Visual] = field(default_factory=dict)
    dirty_json: dict[Path, dict[str, Any]] = field(default_factory=dict)
    created_dirs: set[Path] = field(default_factory=set)
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    # ApplySession lifecycle -------------------------------------------------

    def begin(self) -> None:
        """Start the buffered unit of work."""

    def commit(self) -> None:
        """Flush staged operations to disk.

        Commit is the only normal filesystem mutation point for the buffered
        path. A definition snapshot is retained around the flush so a write
        failure during this early implementation does not leave a partially
        materialized report definition behind.
        """
        if self.dry_run:
            return

        snapshot_parent = tempfile.TemporaryDirectory()
        snapshot_dir = Path(snapshot_parent.name) / "definition"
        shutil.copytree(self.project.definition_folder, snapshot_dir)
        try:
            self._flush_to_project_root(self.project.root)
        except Exception:
            restore_definition_snapshot(self.project, snapshot_dir)
            self.rollback()
            self.project.clear_caches()
            raise
        finally:
            snapshot_parent.cleanup()

        self.project.clear_caches()

    def rollback(self) -> None:
        """Discard staged operations."""
        self.dirty_pages.clear()
        self.dirty_visuals.clear()
        self.dirty_json.clear()
        self.created_dirs.clear()

    def cleanup(self) -> None:
        """Release buffered-session resources."""
        if self.temp_dir is not None:
            self.temp_dir.cleanup()
            self.temp_dir = None

    def project_for_validation(self) -> Project:
        """Return a materialized project containing staged buffered writes.

        The generic validator reads PBIR files from disk. To preserve eager
        apply semantics without committing yet, the buffered path validates a
        temporary copy of the project with staged operations flushed into it.
        """
        if self.dry_run or (not self.created_dirs and not self.dirty_json):
            return self.project

        if self.temp_dir is not None:
            self.temp_dir.cleanup()
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name) / self.project.root.name
        temp_root.mkdir(parents=True)
        shutil.copy2(self.project.pbip_file, temp_root / self.project.pbip_file.name)
        shutil.copytree(
            self.project.report_folder,
            temp_root / self.project.report_folder.name,
        )
        self._flush_to_project_root(temp_root)
        return Project.find(temp_root / self.project.pbip_file.name)

    # Shared read/cache helpers ---------------------------------------------

    def get_model(self, project: Project | None = None) -> Any | None:
        """Load the semantic model once per apply run, matching eager session."""
        if self.model is _MISSING_MODEL:
            try:
                from pbi.modeling.schema import SemanticModel

                self.model = SemanticModel.load((project or self.project).root)
            except Exception:
                self.model = None
        return self.model

    # PbirWriteSession -------------------------------------------------------

    def save_page(self, page: Page) -> None:
        self.dirty_pages[page.folder] = page
        # Store the live payload reference intentionally: apply mutates
        # Page.data in place after save_page can be called, and commit should
        # mirror eager Page.save() by writing the latest object state.
        self.dirty_json[page.folder / "page.json"] = page.data

    def save_visual(self, visual: Visual) -> None:
        self.dirty_visuals[visual.folder] = visual
        # Store the live payload reference intentionally; see save_page.
        self.dirty_json[visual.folder / "visual.json"] = visual.data

    def create_page(
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        page_id = secrets.token_hex(10)
        page_dir = self.project.definition_folder / "pages" / page_id
        data = {
            "$schema": PAGE_SCHEMA,
            "name": page_id,
            "displayName": display_name,
            "displayOption": display_option,
            "width": width,
            "height": height,
            "visibility": "AlwaysVisible",
        }
        page = Page(folder=page_dir, data=data)

        self.created_dirs.add(page_dir)
        self.created_dirs.add(page_dir / "visuals")
        self.save_page(page)
        self._add_page_to_order(page_id)

        self.project.stage_page_in_cache(page)
        return page

    def create_visual(
        self,
        page: Page,
        visual_type: str,
        *,
        x: int = 0,
        y: int = 0,
        width: int = 300,
        height: int = 200,
        behind: bool = False,
    ) -> Visual:
        from pbi.roles import get_visual_roles

        visual_id = secrets.token_hex(10)
        visual_dir = page.folder / "visuals" / visual_id
        existing = self.project._get_visuals_cached(page)
        if behind:
            min_z = min((visual.position.get("z", 0) for visual in existing), default=0)
            z = min_z - 1000
        else:
            max_z = max((visual.position.get("z", 0) for visual in existing), default=0)
            z = max_z + 1000

        query_state: dict[str, Any] = {}
        for role in get_visual_roles(visual_type):
            query_state[role["name"]] = {"projections": []}

        data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": visual_id,
            "position": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "z": z,
                "tabOrder": len(existing),
            },
            "visual": {
                "visualType": visual_type,
                "query": {"queryState": query_state},
                "objects": {},
            },
        }
        visual = Visual(folder=visual_dir, data=data)
        self.created_dirs.add(visual_dir)
        self.save_visual(visual)
        existing.append(visual)
        existing.sort(
            key=lambda candidate: (
                candidate.position.get("y", 0),
                candidate.position.get("x", 0),
            )
        )
        return visual

    def create_group_container(
        self,
        page: Page,
        *,
        name: str | None = None,
        display_name: str | None = None,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
    ) -> Visual:
        self._unsupported("create_group_container")

    def delete_visual(self, visual: Visual) -> None:
        self._unsupported("delete_visual")

    def write_theme(self, payload: dict[str, Any], *, first_time: bool) -> None:
        self._unsupported("write_theme")

    def write_report(self, payload: dict[str, Any]) -> None:
        self._unsupported("write_report")

    def write_bookmark(
        self, payload: dict[str, Any], *, file_path: Path
    ) -> None:
        self._unsupported("write_bookmark")

    def reconcile_bookmark_groups(
        self, groups: list[tuple[str, str | None]]
    ) -> None:
        self._unsupported("reconcile_bookmark_groups")

    def _flush_to_project_root(self, target_root: Path) -> None:
        for folder in sorted(self.created_dirs):
            self._translate_path(folder, target_root).mkdir(parents=True, exist_ok=True)

        for path, payload in sorted(self.dirty_json.items()):
            target = self._translate_path(path, target_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_json(target, payload)

    def _translate_path(self, path: Path, target_root: Path) -> Path:
        return target_root / path.relative_to(self.project.root)

    def _add_page_to_order(self, page_id: str) -> None:
        meta_path = self.project.definition_folder / "pages" / "pages.json"
        if meta_path in self.dirty_json:
            meta = self.dirty_json[meta_path]
        elif meta_path.exists():
            meta = _read_json(meta_path)
        else:
            meta = {"$schema": PAGES_METADATA_SCHEMA}
        meta.setdefault("pageOrder", []).append(page_id)
        self.dirty_json[meta_path] = meta

    def _unsupported(self, operation: str) -> None:
        raise UnsupportedBufferedOperation(
            f"Buffered apply session does not implement {operation} yet. "
            "Add it in the corresponding vertical slice."
        )
