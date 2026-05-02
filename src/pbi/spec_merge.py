"""Shared spec-merge helper for top-level YAML section apply handlers."""

from __future__ import annotations

import copy
from typing import Any


def merge_spec_into(target: dict[str, Any], updates: dict[str, Any]) -> None:
    """Deep-merge ``updates`` into ``target`` with ``None`` meaning delete.

    Used by top-level YAML section handlers (theme, report) to fold a spec
    section into an existing PBIR document. Non-dict values are deep-copied
    so callers can safely mutate ``target`` afterwards.
    """
    for key, value in updates.items():
        if value is None:
            target.pop(key, None)
            continue
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            merge_spec_into(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
