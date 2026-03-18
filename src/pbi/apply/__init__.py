"""Declarative YAML apply engine for PBI reports."""

from __future__ import annotations

import shutil

from .engine import apply_yaml
from .state import ApplyResult

__all__ = ["ApplyResult", "apply_yaml"]
