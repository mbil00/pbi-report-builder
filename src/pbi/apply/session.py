"""Apply Session protocol and lifecycle helper for the YAML Round-Trip engines.

An Apply Session is the per-run rollback frame for one execution of the apply
engine. The protocol is substrate-agnostic: substrate-specific entry points
(page/visual save vs. TMDL line buffer access) stay on the concrete adapters.
``run_apply`` owns the begin/commit/rollback/cleanup lifecycle so both the
PBIR Report and Semantic Model engines drive the same state machine.
"""

from __future__ import annotations

from typing import Callable, Protocol, TypeVar


class ApplySession(Protocol):
    """Lifecycle hooks the apply engine drives once per run."""

    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def cleanup(self) -> None: ...


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
