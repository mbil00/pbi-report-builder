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
    dirty_json: dict[Path, dict[str, Any]] = field(default_factory=dict)
    created_dirs: set[Path] = field(default_factory=set)
    deleted_dirs: set[Path] = field(default_factory=set)
    unsupported_errors: list[str] = field(default_factory=list)
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
        if self.dry_run or self._has_no_staged_changes():
            return

        snapshot_parent = tempfile.TemporaryDirectory()
        snapshot_dir = Path(snapshot_parent.name) / "definition"
        shutil.copytree(self.project.definition_folder, snapshot_dir)
        try:
            self._flush_to_project_root(self.project.root)
        except Exception:
            self._restore_definition_snapshot_safely(snapshot_dir)
            self.rollback()
            self.project.clear_caches()
            raise
        finally:
            snapshot_parent.cleanup()

        self.project.clear_caches()

    def rollback(self) -> None:
        """Discard staged operations."""
        self.dirty_json.clear()
        self.created_dirs.clear()
        self.deleted_dirs.clear()

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
        if self.dry_run or self._has_no_staged_changes():
            return self.project

        if self.temp_dir is not None:
            self.temp_dir.cleanup()
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name) / self.project.root.name
        temp_root.mkdir(parents=True)
        shutil.copy2(self.project.pbip_file, temp_root / self.project.pbip_file.name)
        temp_report = temp_root / self.project.report_folder.name
        temp_report.mkdir()
        shutil.copytree(
            self.project.definition_folder,
            temp_report / self.project.definition_folder.name,
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
        # Store the live payload reference intentionally: apply mutates
        # Page.data in place after save_page can be called, and commit should
        # mirror eager Page.save() by writing the latest object state.
        self.dirty_json[page.folder / "page.json"] = page.data

    def save_visual(self, visual: Visual) -> None:
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
        """Stage deletion of a visual folder and update in-memory page state."""
        visual_dir = visual.folder
        page_dir = visual_dir.parent.parent

        if "visualGroup" in visual.data:
            page = next(
                (
                    candidate
                    for candidate in self.project.get_pages()
                    if candidate.folder == page_dir
                ),
                None,
            )
            visuals = self.project._get_visuals_cached(page) if page is not None else []
            for candidate in visuals:
                is_child = candidate.data.get("parentGroupName") == visual.name
                if candidate.folder != visual_dir and is_child:
                    candidate.data.pop("parentGroupName", None)
                    self.save_visual(candidate)

        self.deleted_dirs.add(visual_dir)
        self.created_dirs.discard(visual_dir)
        for path in list(self.dirty_json):
            try:
                path.relative_to(visual_dir)
            except ValueError:
                continue
            self.dirty_json.pop(path, None)

        cached = self.project._visuals_cache.get(page_dir)
        if cached is not None:
            cached[:] = [candidate for candidate in cached if candidate.folder != visual_dir]

    def write_theme(self, payload: dict[str, Any], *, first_time: bool) -> None:
        if first_time:
            self._stage_first_time_theme(payload)
            return
        self._stage_existing_theme_update(payload)

    def write_report(self, payload: dict[str, Any]) -> None:
        report_path = self.project.definition_folder / "report.json"
        staged = self.dirty_json.get(report_path)
        if staged is None:
            self.dirty_json[report_path] = payload
            return

        original = _read_json(report_path) if report_path.exists() else {}
        for key, value in payload.items():
            if original.get(key) != value:
                staged[key] = value
        for key in original:
            if key not in payload and key in staged:
                staged.pop(key, None)
        self.dirty_json[report_path] = staged

    def write_bookmark(
        self, payload: dict[str, Any], *, file_path: Path
    ) -> None:
        self.created_dirs.add(file_path.parent)
        self.dirty_json[file_path] = payload

    def reconcile_bookmark_groups(
        self, groups: list[tuple[str, str | None]]
    ) -> None:
        from pbi.bookmarks import _existing_group_id, _load_meta, _meta_path

        meta_path = _meta_path(self.project)
        meta = self.dirty_json.get(meta_path) or _load_meta(self.project)
        id_by_display: dict[str, str] = {}
        for display_name, _group in groups:
            bookmark_name = self._find_bookmark_id_by_display(display_name)
            if bookmark_name:
                id_by_display[display_name] = bookmark_name

        targeted_ids = set(id_by_display.values())
        preserved_items: list[dict[str, Any]] = []
        for item in meta.get("items", []):
            if not isinstance(item, dict):
                continue
            if "children" in item:
                children = [
                    child
                    for child in item.get("children", [])
                    if isinstance(child, str) and child not in targeted_ids
                ]
                if not children:
                    continue
                updated = dict(item)
                updated["children"] = children
                preserved_items.append(updated)
                continue
            name = item.get("name")
            if isinstance(name, str) and name not in targeted_ids:
                preserved_items.append(item)

        grouped_children: dict[str, list[str]] = {}
        grouped_order: list[str] = []
        for display_name, group_name in groups:
            bookmark_id = id_by_display.get(display_name)
            if bookmark_id is None:
                continue
            if not group_name:
                preserved_items.append({"name": bookmark_id})
                continue
            if group_name not in grouped_children:
                grouped_children[group_name] = []
                grouped_order.append(group_name)
            grouped_children[group_name].append(bookmark_id)

        for group_name in grouped_order:
            children = grouped_children[group_name]
            if len(children) == 1:
                preserved_items.append({"name": children[0]})
                continue
            preserved_items.append(
                {
                    "name": _existing_group_id(meta, group_name) or secrets.token_hex(10),
                    "displayName": group_name,
                    "children": children,
                }
            )

        meta["items"] = preserved_items
        self.created_dirs.add(meta_path.parent)
        self.dirty_json[meta_path] = meta

    def drain_unsupported_errors(self) -> list[str]:
        errors = list(dict.fromkeys(self.unsupported_errors))
        self.unsupported_errors.clear()
        return errors

    def _has_no_staged_changes(self) -> bool:
        return not self.created_dirs and not self.deleted_dirs and not self.dirty_json

    def _flush_to_project_root(self, target_root: Path) -> None:
        deleted_dirs = sorted(
            self.deleted_dirs,
            key=lambda candidate: len(candidate.parts),
            reverse=True,
        )
        for folder in deleted_dirs:
            target = self._translate_path(folder, target_root)
            if target.exists():
                shutil.rmtree(target)

        for folder in sorted(self.created_dirs):
            self._translate_path(folder, target_root).mkdir(parents=True, exist_ok=True)

        for path, payload in sorted(self.dirty_json.items()):
            if any(_is_relative_to(path, deleted) for deleted in self.deleted_dirs):
                continue
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

    def _stage_first_time_theme(self, payload: dict[str, Any]) -> None:
        from pbi.schema_refs import REPORT_SCHEMA
        from pbi.themes import (
            _ensure_resource_entry,
            _normalize_resource_packages,
            _registered_resources_dir,
            _remove_resource_items_by_type,
            _theme_filename,
            _validate_theme_name,
        )

        theme_name = _validate_theme_name(payload.get("name", "Theme"))
        theme_filename = _theme_filename(theme_name)
        resources_dir = _registered_resources_dir(self.project)
        theme_path = resources_dir / theme_filename
        self.created_dirs.add(resources_dir)
        self.dirty_json[theme_path] = payload

        report_path = self.project.definition_folder / "report.json"
        report = self.dirty_json.get(report_path) or _read_json(report_path)
        _normalize_resource_packages(report)
        report.setdefault("$schema", REPORT_SCHEMA)
        report.setdefault("themeCollection", {})
        base_theme = report.get("themeCollection", {}).get("baseTheme", {})
        if isinstance(base_theme, dict):
            version_at_import = base_theme.get("reportVersionAtImport", {})
        else:
            version_at_import = {}
        if not isinstance(version_at_import, dict):
            version_at_import = {}
        report["themeCollection"]["customTheme"] = {
            "name": theme_filename,
            "reportVersionAtImport": version_at_import,
            "type": "RegisteredResources",
        }
        report.pop("layoutOptimization", None)
        _remove_resource_items_by_type(report, "CustomTheme")
        _ensure_resource_entry(report, theme_name)
        self.dirty_json[report_path] = report

    def _stage_existing_theme_update(self, payload: dict[str, Any]) -> None:
        from pbi.themes import _custom_theme_paths

        report_path = self.project.definition_folder / "report.json"
        report = self.dirty_json.get(report_path) or _read_json(report_path)
        custom = report.get("themeCollection", {}).get("customTheme")
        if not custom:
            raise FileNotFoundError("No custom theme applied to this project")
        theme_name = custom.get("name", "")
        for candidate in _custom_theme_paths(self.project, report, theme_name):
            if candidate.exists() or candidate in self.dirty_json:
                self.dirty_json[candidate] = payload
                return
        raise FileNotFoundError(
            f'Theme file for "{theme_name}" not found in RegisteredResources'
        )

    def _find_bookmark_id_by_display(self, display_name: str) -> str | None:
        bookmarks_dir = self.project.definition_folder / "bookmarks"
        for path, payload in self.dirty_json.items():
            if path.parent == bookmarks_dir and path.name.endswith(".bookmark.json"):
                if payload.get("displayName") == display_name:
                    name = payload.get("name")
                    return name if isinstance(name, str) and name else None

        if not bookmarks_dir.exists():
            return None
        for path in sorted(bookmarks_dir.glob("*.bookmark.json")):
            if any(_is_relative_to(path, deleted) for deleted in self.deleted_dirs):
                continue
            try:
                payload = _read_json(path)
            except Exception:
                continue
            if payload.get("displayName") == display_name:
                name = payload.get("name")
                return name if isinstance(name, str) and name else None
        return None

    def _restore_definition_snapshot_safely(self, snapshot_dir: Path) -> None:
        """Restore definition without deleting the only on-disk copy first."""
        definition = self.project.definition_folder
        restore_dir = definition.with_name(f".{definition.name}.restore")
        failed_dir = definition.with_name(f".{definition.name}.failed")
        if restore_dir.exists():
            shutil.rmtree(restore_dir)
        if failed_dir.exists():
            shutil.rmtree(failed_dir)
        shutil.copytree(snapshot_dir, restore_dir)
        if definition.exists():
            definition.rename(failed_dir)
        try:
            restore_dir.rename(definition)
        except Exception:
            if failed_dir.exists() and not definition.exists():
                failed_dir.rename(definition)
            raise
        if failed_dir.exists():
            shutil.rmtree(failed_dir)

    def _unsupported(self, operation: str, *, fatal: bool = True) -> None:
        message = (
            f"Buffered apply session does not implement {operation} yet. "
            "Add it in the corresponding vertical slice."
        )
        self.unsupported_errors.append(message)
        if fatal:
            raise UnsupportedBufferedOperation(message)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
