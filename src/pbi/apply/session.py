"""Apply Session protocols and lifecycle helper for the YAML Round-Trip engines.

An Apply Session is the per-run rollback frame for one execution of the apply
engine. The lifecycle protocol is substrate-agnostic: substrate-specific entry
points stay on per-substrate write protocols. ``run_apply`` owns the
begin/commit/rollback/cleanup lifecycle so both the PBIR Report and Semantic
Model engines drive the same state machine.

The ``PbirWriteSession`` protocol below is the PBIR-specific write seam that
apply leaf code uses instead of touching ``ReportAuthoring`` / ``Visual.save``
/ ``Page.save`` / ``save_theme_data`` / ``write_report_json`` / bookmark I/O
directly. The concrete adapter (``PbirApplySession``) absorbs the snapshot
guard so leaf code cannot forget to take it.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar

from pbi.project import Page, Visual


class ApplySession(Protocol):
    """Lifecycle hooks the apply engine drives once per run."""

    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def cleanup(self) -> None: ...


class PbirWriteSession(Protocol):
    """PBIR Report write seam.

    Every filesystem-mutating operation against the PBIR Report substrate goes
    through a method on this protocol. Adapters absorb the snapshot guard so
    apply leaf code cannot bypass rollback by reaching for ``Visual.save`` /
    ``Page.save`` / ``ReportAuthoring`` directly.
    """

    # Per-entity persistence ------------------------------------------------
    def save_page(self, page: Page) -> None: ...
    def save_visual(self, visual: Visual) -> None: ...

    # Page/visual structure -------------------------------------------------
    def create_page(
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page: ...
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
    ) -> Visual: ...
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
    ) -> Visual: ...
    def delete_visual(self, visual: Visual) -> None: ...

    # Doc-level writes ------------------------------------------------------
    def write_theme(self, payload: dict[str, Any], *, first_time: bool) -> None: ...
    def write_report(self, payload: dict[str, Any]) -> None: ...
    def write_bookmark(self, payload: dict[str, Any]) -> None: ...
    def reconcile_bookmark_groups(
        self, groups: list[tuple[str, str | None]]
    ) -> None: ...


class ApplyDiagnostics(Protocol):
    """Result shape that ``run_apply`` inspects to decide commit vs rollback."""

    errors: list[str]
    rolled_back: bool


R = TypeVar("R", bound=ApplyDiagnostics)


def run_apply(
    session: ApplySession,
    body: Callable[[], R],
    *,
    continue_on_error: bool = False,
) -> R:
    """Run ``body`` inside the session lifecycle.

    Three terminating paths:
      * Body raises — rollback, cleanup, re-raise.
      * Body returns with errors and ``continue_on_error`` is False — rollback,
        mark ``result.rolled_back``, cleanup, return.
      * Otherwise — commit, cleanup, return.
    """
    session.begin()
    try:
        try:
            result = body()
        except Exception:
            session.rollback()
            raise
        if result.errors and not continue_on_error:
            session.rollback()
            result.rolled_back = True
        else:
            session.commit()
        return result
    finally:
        session.cleanup()
