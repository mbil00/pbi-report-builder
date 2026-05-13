"""Experimental buffered PBIR apply session.

This module is the secondary apply path used to grow toward a future
session/daemon architecture. The class intentionally starts as a skeleton: it
satisfies the same write-session protocol as the eager ``PbirApplySession`` so
parity tests can be added first, then staged operations can be implemented one
vertical slice at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi.project import Page, Project, Visual


_MISSING_MODEL = object()


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

    # ApplySession lifecycle -------------------------------------------------

    def begin(self) -> None:
        """Start the buffered unit of work."""

    def commit(self) -> None:
        """Flush staged operations.

        Slice 0 has no staged operations yet; later slices will make this the
        only place where the buffered path mutates the PBIR filesystem.
        """

    def rollback(self) -> None:
        """Discard staged operations."""

    def cleanup(self) -> None:
        """Release buffered-session resources."""

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
        self._unsupported("save_page")

    def save_visual(self, visual: Visual) -> None:
        self._unsupported("save_visual")

    def create_page(
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        self._unsupported("create_page")

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
        self._unsupported("create_visual")

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

    def _unsupported(self, operation: str) -> None:
        raise NotImplementedError(
            f"Buffered apply session does not implement {operation} yet. "
            "Add it in the corresponding vertical slice."
        )
