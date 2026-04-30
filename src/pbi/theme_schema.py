"""Static schema for theme document properties.

Counterpart to ``visual_schema``: where the visual schema is dynamic
(per-visual-type, extended at runtime by custom visuals), the theme schema
is closed and authoritative — every writable property is known up front,
so writes can be hard-rejected.

Public surface:

- ``ThemeProperty`` — dataclass describing one writable theme property.
- ``THEME_PROPERTIES`` — list of ``(path, type, description)`` tuples for
  iteration in CLI output (back-compat shape for older callers).
- ``lookup_property(path)`` — O(1) lookup; returns ``None`` if unknown.
- ``validate_and_encode(path, raw)`` — the seam every theme document write
  goes through. Raises ``ValueError`` on unknown property or bad value.
  Returns the encoded JSON value ready to write into the theme document.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from pbi.theme_styles import _validate_hex_color


@dataclass(frozen=True)
class ThemeProperty:
    path: str
    prop_type: str
    description: str


_THEME_PROPERTY_DEFS: list[ThemeProperty] = [
    ThemeProperty("foreground", "color", "Primary text color"),
    ThemeProperty("foregroundNeutralSecondary", "color", "Secondary text color"),
    ThemeProperty("foregroundNeutralTertiary", "color", "Tertiary/muted text color"),
    ThemeProperty("background", "color", "Page background color"),
    ThemeProperty("backgroundLight", "color", "Light background (cards, wells)"),
    ThemeProperty("backgroundNeutral", "color", "Neutral background"),
    ThemeProperty("tableAccent", "color", "Accent color (table headers, highlights)"),
    ThemeProperty("hyperlink", "color", "Hyperlink color"),
    ThemeProperty("visitedHyperlink", "color", "Visited hyperlink color"),
    ThemeProperty("good", "color", "Positive/good sentiment color"),
    ThemeProperty("neutral", "color", "Neutral sentiment color"),
    ThemeProperty("bad", "color", "Negative/bad sentiment color"),
    ThemeProperty("maximum", "color", "Maximum value color (conditional formatting)"),
    ThemeProperty("center", "color", "Center value color (conditional formatting)"),
    ThemeProperty("minimum", "color", "Minimum value color (conditional formatting)"),
    ThemeProperty("null", "color", "Null value color"),
    ThemeProperty("dataColors", "color[]", "Comma-separated data series colors"),
    ThemeProperty("textClasses.title.fontSize", "number", "Title font size"),
    ThemeProperty("textClasses.title.fontFace", "string", "Title font face"),
    ThemeProperty("textClasses.title.color", "color", "Title text color"),
    ThemeProperty("textClasses.header.fontSize", "number", "Header font size"),
    ThemeProperty("textClasses.header.fontFace", "string", "Header font face"),
    ThemeProperty("textClasses.header.color", "color", "Header text color"),
    ThemeProperty("textClasses.callout.fontSize", "number", "Callout font size"),
    ThemeProperty("textClasses.callout.fontFace", "string", "Callout font face"),
    ThemeProperty("textClasses.callout.color", "color", "Callout text color"),
    ThemeProperty("textClasses.label.fontSize", "number", "Label font size"),
    ThemeProperty("textClasses.label.fontFace", "string", "Label font face"),
    ThemeProperty("textClasses.label.color", "color", "Label text color"),
]


_THEME_PROPERTY_INDEX: dict[str, ThemeProperty] = {
    prop.path: prop for prop in _THEME_PROPERTY_DEFS
}


THEME_PROPERTIES: list[tuple[str, str, str]] = [
    (prop.path, prop.prop_type, prop.description) for prop in _THEME_PROPERTY_DEFS
]


def lookup_property(prop_path: str) -> ThemeProperty | None:
    return _THEME_PROPERTY_INDEX.get(prop_path)


def list_properties() -> list[ThemeProperty]:
    return list(_THEME_PROPERTY_DEFS)


def validate_and_encode(prop_path: str, raw_value: str) -> Any:
    """Validate a theme property write and return the encoded JSON value.

    Raises ``ValueError`` on unknown property or invalid value.
    """
    prop = _THEME_PROPERTY_INDEX.get(prop_path)
    if prop is None:
        raise ValueError(_unknown_property_message(prop_path))
    return _encode(prop, raw_value)


def _encode(prop: ThemeProperty, raw_value: str) -> Any:
    if prop.prop_type == "color":
        return _validate_hex_color(raw_value)
    if prop.prop_type == "color[]":
        parts = [c.strip() for c in raw_value.split(",") if c.strip()]
        if not parts:
            raise ValueError(f"{prop.path}: at least one color required")
        return [_validate_hex_color(c) for c in parts]
    if prop.prop_type == "number":
        try:
            return int(raw_value)
        except ValueError:
            try:
                return float(raw_value)
            except ValueError as exc:
                raise ValueError(
                    f"{prop.path}: '{raw_value}' is not a valid number"
                ) from exc
    if prop.prop_type == "string":
        return raw_value
    raise ValueError(f"{prop.path}: unsupported schema type '{prop.prop_type}'")


def _unknown_property_message(prop_path: str) -> str:
    candidates = list(_THEME_PROPERTY_INDEX.keys())
    matches = difflib.get_close_matches(prop_path, candidates, n=3, cutoff=0.5)
    if matches:
        suggestion = ", ".join(f'"{m}"' for m in matches)
        return f'Unknown theme property "{prop_path}". Did you mean: {suggestion}?'
    return f'Unknown theme property "{prop_path}".'
