"""Internal state and persistence helpers for the report apply engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.apply.rollback import RollbackJournal
from pbi.apply.session import PbirWriteSession
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
class PbirApplySession:
    """Apply Session adapter for the PBIR Report definition substrate.

    Implements both ``ApplySession`` (lifecycle) and ``PbirWriteSession``
    (write seam). Writes are eager (``Page.save`` / ``Visual.save`` write
    straight to disk) so commit is a no-op; rollback restores touched paths
    from a lazily-created rollback journal.

    Per-entity persistence (``save_visual``, ``save_page``) and structural
    creation/deletion (``create_page``, ``create_visual``,
    ``create_group_container``, ``delete_visual``) are implemented here and
    each absorbs rollback journaling. Apply leaf code reaches the PBIR
    substrate exclusively through these methods; nothing under
    ``src/pbi/apply/`` imports ``ReportAuthoring`` anymore.

    Doc-level writes (``write_theme``, ``write_report``, ``write_bookmark``,
    ``reconcile_bookmark_groups``) are also implemented and each absorbs
    rollback journaling. The bookmarks meta file is written exactly once per
    apply, by ``reconcile_bookmark_groups``; per-bookmark ``write_bookmark``
    calls touch only the individual bookmark JSON file.
    """

    project: Project
    dry_run: bool
    rollback_journal: RollbackJournal | None = None
    model: Any = _MISSING_MODEL

    def ensure_rollback_journal(self) -> None:
        """Create the rollback journal lazily on the first write-intent path."""
        if self.dry_run or self.rollback_journal is not None:
            return
        self.rollback_journal = RollbackJournal(root=self.project.root)

    def get_model(self, project: Project | None = None) -> Any | None:
        """Load the semantic model once per apply run."""
        if self.model is _MISSING_MODEL:
            try:
                from pbi.modeling.schema import SemanticModel

                self.model = SemanticModel.load(self.project.root)
            except Exception:
                self.model = None
        return self.model

    # ApplySession lifecycle -------------------------------------------------

    def begin(self) -> None:
        """No-op: rollback journal stays lazy until the first write-intent path."""

    def commit(self) -> None:
        """No-op: page/visual saves are eager, nothing to flush."""

    def rollback(self) -> None:
        """Restore touched paths from the rollback journal, if one was taken."""
        if self.rollback_journal is not None:
            self.rollback_journal.restore()
        self.project.clear_caches()

    def cleanup(self) -> None:
        self.rollback_journal = None

    def project_for_validation(self) -> Project:
        """Return the project state validation should inspect."""
        return self.project

    # PbirWriteSession -------------------------------------------------------

    def save_visual(self, visual: Visual) -> None:
        """Persist a Visual, journaling the previous file state if needed."""
        self.ensure_rollback_journal()
        self._capture_file(visual.folder / "visual.json")
        visual.save()

    def save_page(self, page: Page) -> None:
        """Persist a Page, journaling the previous file state if needed."""
        self.ensure_rollback_journal()
        self._capture_file(page.folder / "page.json")
        page.save()

    def create_page(
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        """Create a Page on the project, journaling rollback state."""
        from pbi.report_authoring import ReportAuthoring  # composed by adapter

        self.ensure_rollback_journal()
        self._capture_file(self.project.definition_folder / "pages" / "pages.json")
        page = ReportAuthoring(self.project).create_page(
            display_name,
            width=width,
            height=height,
            display_option=display_option,
        )
        self._record_created_dir(page.folder)
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
        """Create a Visual on a Page, journaling rollback state."""
        from pbi.report_authoring import ReportAuthoring  # composed by adapter

        self.ensure_rollback_journal()
        visual = ReportAuthoring(self.project).create_visual(
            page,
            visual_type,
            x=x,
            y=y,
            width=width,
            height=height,
            behind=behind,
        )
        self._record_created_dir(visual.folder)
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
        """Create an empty group container Visual, journaling rollback state."""
        from pbi.report_authoring import ReportAuthoring  # composed by adapter

        self.ensure_rollback_journal()
        visual = ReportAuthoring(self.project).create_group_container(
            page,
            name=name,
            display_name=display_name,
            x=x,
            y=y,
            width=width,
            height=height,
        )
        self._record_created_dir(visual.folder)
        return visual

    def delete_visual(self, visual: Visual) -> None:
        """Delete a Visual, journaling rollback state."""
        from pbi.report_authoring import ReportAuthoring  # composed by adapter

        self.ensure_rollback_journal()
        self._capture_visual_delete_side_effects(visual)
        self._capture_deleted_tree(visual.folder)
        ReportAuthoring(self.project).delete_visual(visual)

    def write_theme(self, payload: dict[str, Any], *, first_time: bool) -> None:
        """Persist a planned theme payload, journaling rollback state.

        ``first_time`` selects the write path: when no custom theme exists yet
        we route through ``apply_theme`` (copies into RegisteredResources and
        wires up ``themeCollection``); when one exists we ``save_theme_data``
        in place.

        Theme writes journal both ``report.json`` and registered resource
        files so rollback can restore the whole report tree without copying
        it up front.
        """
        from pbi.themes import apply_theme_data, save_theme_data  # composed by adapter

        self.ensure_rollback_journal()
        self._capture_file(self.project.definition_folder / "report.json")
        self._capture_theme_side_effects(payload, first_time=first_time)
        if first_time:
            apply_theme_data(self.project, payload)
        else:
            save_theme_data(self.project, payload)

    def write_report(self, payload: dict[str, Any]) -> None:
        """Persist a planned ``report.json`` payload, journaling previous state."""
        from pbi.report_io import write_report_json  # composed by adapter

        self.ensure_rollback_journal()
        self._capture_file(self.project.definition_folder / "report.json")
        write_report_json(self.project, payload)

    def write_bookmark(
        self, payload: dict[str, Any], *, file_path: Path
    ) -> None:
        """Persist a single bookmark JSON to disk, journaling previous state.

        Writes only the bookmark file -- the bookmarks meta file is the
        responsibility of ``reconcile_bookmark_groups`` exclusively, so the
        meta is written exactly once per apply with the full group hierarchy.
        """
        from pbi.project import _write_json  # composed by adapter

        self.ensure_rollback_journal()
        self._capture_created_dir(file_path.parent)
        self._capture_file(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(file_path, payload)

    def reconcile_bookmark_groups(
        self, groups: list[tuple[str, str | None]]
    ) -> None:
        """Write the bookmarks meta file with the full group hierarchy."""
        from pbi.bookmarks import (  # composed by adapter
            _meta_path,
            reconcile_bookmark_groups as _reconcile,
        )

        self.ensure_rollback_journal()
        meta_path = _meta_path(self.project)
        self._capture_created_dir(meta_path.parent)
        self._capture_file(meta_path)
        _reconcile(self.project, groups)

    def _capture_file(self, path: Path) -> None:
        if self.rollback_journal is not None:
            self.rollback_journal.capture_file(path)

    def _capture_created_dir(self, path: Path) -> None:
        if self.rollback_journal is not None:
            self.rollback_journal.capture_created_dir(path)

    def _record_created_dir(self, path: Path) -> None:
        if self.rollback_journal is not None:
            self.rollback_journal.record_created_dir(path)

    def _capture_deleted_tree(self, path: Path) -> None:
        if self.rollback_journal is not None:
            self.rollback_journal.capture_deleted_tree(path)

    def _capture_visual_delete_side_effects(self, visual: Visual) -> None:
        if "visualGroup" not in visual.data:
            return
        page_path = visual.folder.parent.parent
        page = next(
            (
                candidate
                for candidate in self.project.get_pages()
                if candidate.folder == page_path
            ),
            None,
        )
        if page is None:
            return
        for candidate in self.project.get_visuals(page):
            if candidate.data.get("parentGroupName") == visual.name:
                self._capture_file(candidate.folder / "visual.json")

    def _capture_theme_side_effects(
        self,
        payload: dict[str, Any],
        *,
        first_time: bool,
    ) -> None:
        from pbi.themes import (
            _custom_theme_paths,
            _registered_resources_dir,
            _theme_filename,
            _validate_theme_name,
        )

        report = self.project.get_report_meta()
        resources_dir = _registered_resources_dir(self.project)
        self._capture_created_dir(resources_dir)
        if first_time:
            theme_name = _validate_theme_name(payload.get("name", "Theme"))
            self._capture_file(resources_dir / _theme_filename(theme_name))
        else:
            custom = report.get("themeCollection", {}).get("customTheme")
            if isinstance(custom, dict):
                for path in _custom_theme_paths(self.project, report, custom.get("name", "")):
                    self._capture_file(path)


def save_page_if_changed(
    project: Project,
    page: Page,
    *,
    original_data: dict,
    session: PbirWriteSession,
) -> bool:
    """Persist page changes only when the serialized content changed.

    Typed against ``PbirWriteSession`` rather than ``PbirApplySession`` so a
    test fake satisfying the protocol can substitute without touching disk.
    """
    del project  # unused: ``session.save_page`` absorbs rollback journaling
    if page.data == original_data:
        return False
    session.save_page(page)
    return True


def save_visual_if_changed(
    project: Project,
    visual: Visual,
    *,
    original_data: dict,
    session: PbirWriteSession,
) -> bool:
    """Persist visual changes only when the serialized content changed.

    Typed against ``PbirWriteSession`` rather than ``PbirApplySession`` so a
    test fake satisfying the protocol can substitute without touching disk.
    """
    del project  # unused: ``session.save_visual`` absorbs rollback journaling
    if visual.data == original_data:
        return False
    session.save_visual(visual)
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
