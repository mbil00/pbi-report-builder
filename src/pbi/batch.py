"""Buffered project write helpers for CLI batch mutations.

The apply engine has a full rollback-capable buffered session because it owns
complex create/update/delete workflows. CLI batch commands mostly need a smaller
unit-of-work: accumulate page/visual edits, skip no-op payloads, then flush each
changed PBIR file once at the end.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.project import Page, Project, Visual


@dataclass
class BatchProjectWriter:
    """Collect changed pages/visuals and flush them once.

    Commands can either stage an already-prepared replacement payload with
    ``stage_visual_data`` / ``stage_page_data`` or track in-place mutations with
    ``track_visual`` / ``track_page`` followed by ``stage_tracked``.
    """

    project: Project
    _dirty_pages: list[Page] = field(default_factory=list)
    _dirty_visuals: list[Visual] = field(default_factory=list)
    _page_snapshots: dict[Path, dict[str, Any]] = field(default_factory=dict)
    _visual_snapshots: dict[Path, dict[str, Any]] = field(default_factory=dict)

    @property
    def dirty_page_count(self) -> int:
        return _unique_path_count(page.folder / "page.json" for page in self._dirty_pages)

    @property
    def dirty_visual_count(self) -> int:
        return _unique_path_count(visual.folder / "visual.json" for visual in self._dirty_visuals)

    def stage_page_data(self, page: Page, data: dict[str, Any]) -> bool:
        """Replace page data only when it differs and mark it dirty."""
        if page.data == data:
            return False
        page.data = data
        self.mark_page(page)
        return True

    def stage_visual_data(self, visual: Visual, data: dict[str, Any]) -> bool:
        """Replace visual data only when it differs and mark it dirty."""
        if visual.data == data:
            return False
        visual.data = data
        self.mark_visual(visual)
        return True

    def mark_page(self, page: Page) -> None:
        self._dirty_pages.append(page)

    def mark_visual(self, visual: Visual) -> None:
        self._dirty_visuals.append(visual)

    def track_page(self, page: Page) -> None:
        self._page_snapshots.setdefault(page.folder, copy.deepcopy(page.data))

    def track_visual(self, visual: Visual) -> None:
        self._visual_snapshots.setdefault(visual.folder, copy.deepcopy(visual.data))

    def track_pages(self, pages: list[Page]) -> None:
        for page in pages:
            self.track_page(page)

    def track_visuals(self, visuals: list[Visual]) -> None:
        for visual in visuals:
            self.track_visual(visual)

    def stage_tracked_page(self, page: Page) -> bool:
        snapshot = self._page_snapshots.get(page.folder)
        if snapshot is None or snapshot == page.data:
            return False
        self.mark_page(page)
        return True

    def stage_tracked_visual(self, visual: Visual) -> bool:
        snapshot = self._visual_snapshots.get(visual.folder)
        if snapshot is None or snapshot == visual.data:
            return False
        self.mark_visual(visual)
        return True

    def stage_tracked_pages(self, pages: list[Page]) -> int:
        return sum(1 for page in pages if self.stage_tracked_page(page))

    def stage_tracked_visuals(self, visuals: list[Visual]) -> int:
        return sum(1 for visual in visuals if self.stage_tracked_visual(visual))

    def commit(self) -> None:
        """Flush all dirty PBIR files once each."""
        self.project.save_pages(self._dirty_pages)
        self.project.save_visuals(self._dirty_visuals)


def _unique_path_count(paths) -> int:
    return len(set(paths))
