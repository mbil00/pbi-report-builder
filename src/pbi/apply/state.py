"""Internal state and persistence helpers for the report apply engine."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.lookup import find_visual_by_identifier
from pbi.project import Page, Project, Visual


@dataclass
class ApplyResult:
    """Summary of what was changed by an apply operation."""

    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    visuals_created: list[tuple[str, str]] = field(default_factory=list)
    visuals_updated: list[tuple[str, str]] = field(default_factory=list)
    visuals_deleted: list[tuple[str, str]] = field(default_factory=list)
    properties_set: int = 0
    bindings_added: int = 0
    filters_added: int = field(default=0)
    interactions_set: list[tuple[str, str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rolled_back: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(
            self.pages_created or self.pages_updated
            or self.visuals_created or self.visuals_updated
            or self.visuals_deleted
        )


_MISSING_MODEL = object()


@dataclass
class ApplySession:
    """Per-run caches and rollback bookkeeping for apply."""

    dry_run: bool
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    snapshot_dir: Path | None = None
    model: Any = _MISSING_MODEL

    def ensure_snapshot(self, project: Project) -> None:
        """Create the definition snapshot lazily on the first write-intent path."""
        if self.dry_run or self.snapshot_dir is not None:
            return
        self.temp_dir = tempfile.TemporaryDirectory()
        self.snapshot_dir = Path(self.temp_dir.name) / "definition"
        shutil.copytree(project.definition_folder, self.snapshot_dir)

    def restore(self, project: Project) -> None:
        if self.snapshot_dir is None:
            return
        restore_definition_snapshot(project, self.snapshot_dir)
        project.clear_caches()

    def get_model(self, project: Project) -> Any | None:
        """Load the semantic model once per apply run."""
        if self.model is _MISSING_MODEL:
            try:
                from pbi.modeling.schema import SemanticModel

                self.model = SemanticModel.load(project.root)
            except Exception:
                self.model = None
        return self.model

    def cleanup(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


def save_page_if_changed(
    project: Project,
    page: Page,
    *,
    original_data: dict,
    session: ApplySession,
) -> bool:
    """Persist page changes only when the serialized content changed."""
    if page.data == original_data:
        return False
    session.ensure_snapshot(project)
    page.save()
    return True


def save_visual_if_changed(
    project: Project,
    visual: Visual,
    *,
    original_data: dict,
    session: ApplySession,
) -> bool:
    """Persist visual changes only when the serialized content changed."""
    if visual.data == original_data:
        return False
    session.ensure_snapshot(project)
    visual.save()
    return True


def sort_visuals(visuals: list[Visual]) -> None:
    """Sort visuals by top-left position, matching existing list behavior."""
    visuals.sort(
        key=lambda visual: (
            visual.position.get("y", 0),
            visual.position.get("x", 0),
        )
    )


@dataclass
class PageVisualState:
    """Per-page visual state reused across one apply pass."""

    page: Page
    visuals: list[Visual]
    _by_folder: dict[str, Visual] = field(default_factory=dict, init=False, repr=False)
    _by_name: dict[str, Visual] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        sort_visuals(self.visuals)
        self._reindex()

    def _reindex(self) -> None:
        self._by_folder = {}
        self._by_name = {}
        for visual in self.visuals:
            self._by_folder.setdefault(visual.folder.name, visual)
            self._by_name.setdefault(visual.name, visual)

    def add(self, visual: Visual) -> None:
        self.visuals.append(visual)
        sort_visuals(self.visuals)
        self._reindex()

    def remove(self, visual: Visual) -> None:
        self.visuals[:] = [candidate for candidate in self.visuals if candidate.folder != visual.folder]
        self._reindex()

    def refresh(self) -> None:
        sort_visuals(self.visuals)
        self._reindex()

    def find_visual(self, identifier: str) -> Visual:
        return find_visual_by_identifier(
            self.visuals,
            identifier,
            page_display_name=self.page.display_name,
            folder_name=lambda visual: visual.folder.name,
            visual_name=lambda visual: visual.name,
            visual_type=lambda visual: visual.visual_type,
            by_folder=self._by_folder,
            by_name=self._by_name,
        )


def restore_definition_snapshot(project: Project, snapshot_dir: Path) -> None:
    """Restore the report definition directory from a pre-apply snapshot."""
    if project.definition_folder.exists():
        shutil.rmtree(project.definition_folder)
    shutil.copytree(snapshot_dir, project.definition_folder)
