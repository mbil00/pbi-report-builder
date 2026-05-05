"""In-memory test fakes that satisfy the apply-session protocols.

``FakePbirWriteSession`` records every call into the PBIR write seam without
touching disk. Apply-leaf tests pass it where the leaf code expects a session
adapter. Future slices that migrate more leaf paths through the session reuse
this fake from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.project import Page, Visual


@dataclass
class FakePbirWriteSession:
    """In-memory call recorder satisfying ``PbirWriteSession``.

    Each method appends a ``(method_name, args_tuple)`` entry to ``calls`` so
    apply-leaf tests can assert the call sequence. The lifecycle hooks
    (``begin``/``commit``/``rollback``/``cleanup``) and the legacy
    ``ensure_snapshot`` / ``get_model`` accessors are also recorded so the
    fake can stand in wherever ``PbirApplySession`` would.

    ``create_*`` methods that would normally return a ``Page`` / ``Visual``
    return ``None``; tests that exercise those code paths must override the
    fake to supply an entity (or wait for follow-up slices that build on top
    of those operations).
    """

    calls: list[tuple[Any, ...]] = field(default_factory=list)
    model: Any = None

    # ApplySession lifecycle -------------------------------------------------

    def begin(self) -> None:
        self.calls.append(("begin",))

    def commit(self) -> None:
        self.calls.append(("commit",))

    def rollback(self) -> None:
        self.calls.append(("rollback",))

    def cleanup(self) -> None:
        self.calls.append(("cleanup",))

    # PbirApplySession-shaped accessors retained on the concrete adapter -----

    def ensure_snapshot(self, project: Any | None = None) -> None:
        self.calls.append(("ensure_snapshot",))

    def get_model(self, project: Any | None = None) -> Any:
        return self.model

    # PbirWriteSession -------------------------------------------------------

    def save_page(self, page: Page) -> None:
        self.calls.append(("save_page", page))

    def save_visual(self, visual: Visual) -> None:
        self.calls.append(("save_visual", visual))

    def create_page(
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        self.calls.append(
            ("create_page", display_name, width, height, display_option)
        )
        return None  # type: ignore[return-value]

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
        self.calls.append(
            ("create_visual", page, visual_type, x, y, width, height, behind)
        )
        return None  # type: ignore[return-value]

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
        self.calls.append(
            (
                "create_group_container",
                page,
                name,
                display_name,
                x,
                y,
                width,
                height,
            )
        )
        return None  # type: ignore[return-value]

    def delete_visual(self, visual: Visual) -> None:
        self.calls.append(("delete_visual", visual))

    def write_theme(self, payload: dict[str, Any], *, first_time: bool) -> None:
        self.calls.append(("write_theme", payload, first_time))

    def write_report(self, payload: dict[str, Any]) -> None:
        self.calls.append(("write_report", payload))

    def write_bookmark(
        self, payload: dict[str, Any], *, file_path: Path
    ) -> None:
        self.calls.append(("write_bookmark", payload, file_path))

    def reconcile_bookmark_groups(
        self, groups: list[tuple[str, str | None]]
    ) -> None:
        self.calls.append(("reconcile_bookmark_groups", groups))

    # Helpers ----------------------------------------------------------------

    def call_names(self) -> list[str]:
        """Return just the method names recorded on this fake, in order."""
        return [call[0] for call in self.calls]
