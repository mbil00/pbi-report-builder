"""Theme override audit helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pbi.project import Project

from .theme_styles import decode_theme_style_value


@dataclass
class ThemeOverrideEntry:
    """A per-visual property that overrides a theme default."""

    page_name: str
    visual_name: str
    visual_type: str
    object_name: str
    property_name: str
    visual_value: str
    theme_value: str
    is_match: bool
    _objects_key: str = ""
    _entry_idx: int = 0


@dataclass
class ThemeAuditResult:
    """Summary of a theme override audit."""

    overrides: list[ThemeOverrideEntry]
    total_visuals: int = 0
    visuals_with_overrides: int = 0

    @property
    def redundant_count(self) -> int:
        return sum(1 for entry in self.overrides if entry.is_match)

    @property
    def conflict_count(self) -> int:
        return sum(1 for entry in self.overrides if not entry.is_match)


def _build_theme_defaults(data: dict) -> dict[tuple[str, str, str], Any]:
    """Build lookup of theme defaults: (visual_type, object, property) -> decoded value."""
    defaults: dict[tuple[str, str, str], Any] = {}
    visual_styles = data.get("visualStyles", {})
    for visual_type, roles in visual_styles.items():
        if not isinstance(roles, dict):
            continue
        for objects in roles.values():
            if not isinstance(objects, dict):
                continue
            for object_name, entries in objects.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    for property_name, raw_value in entry.items():
                        if property_name == "$id":
                            continue
                        defaults[(visual_type, object_name, property_name)] = decode_theme_style_value(raw_value)
    return defaults


def _lookup_theme_default(
    defaults: dict[tuple[str, str, str], Any],
    visual_type: str,
    object_name: str,
    property_name: str,
) -> tuple[Any, bool]:
    """Look up theme default: type-specific first, then wildcard."""
    key = (visual_type, object_name, property_name)
    if key in defaults:
        return defaults[key], True
    wildcard_key = ("*", object_name, property_name)
    if wildcard_key in defaults:
        return defaults[wildcard_key], True
    return None, False


def _decode_visual_value(raw: Any) -> Any:
    """Decode a per-visual PBI property value to human-readable form."""
    from pbi.properties import decode_pbi_value

    return decode_pbi_value(raw)


def _values_match(visual_val: Any, theme_val: Any) -> bool:
    """Compare decoded visual and theme values."""
    if isinstance(visual_val, str) and isinstance(theme_val, str):
        return visual_val.upper() == theme_val.upper()
    return visual_val == theme_val


def audit_theme_overrides_from_data(
    project: Project,
    data: dict,
    *,
    page_filter: str | None = None,
) -> ThemeAuditResult:
    """Scan all visuals for properties that override theme defaults."""
    defaults = _build_theme_defaults(data)
    if not defaults:
        return ThemeAuditResult(overrides=[])

    result = ThemeAuditResult(overrides=[])
    pages = project.get_pages()
    if page_filter:
        pages = [project.find_page(page_filter)]

    for page in pages:
        for visual in project.get_visuals(page):
            if "visualGroup" in visual.data:
                continue
            result.total_visuals += 1
            visual_type = visual.visual_type
            visual_has_override = False

            for objects_key in ("objects", "visualContainerObjects"):
                objects = visual.data.get("visual", {}).get(objects_key, {})
                for object_name, entries in objects.items():
                    if not isinstance(entries, list):
                        continue
                    for entry_idx, entry in enumerate(entries):
                        properties = entry.get("properties", {})
                        if not isinstance(properties, dict):
                            continue
                        for property_name, raw_value in properties.items():
                            theme_value, found = _lookup_theme_default(
                                defaults,
                                visual_type,
                                object_name,
                                property_name,
                            )
                            if not found:
                                continue
                            visual_value = _decode_visual_value(raw_value)
                            is_match = _values_match(visual_value, theme_value)
                            result.overrides.append(
                                ThemeOverrideEntry(
                                    page_name=page.display_name,
                                    visual_name=visual.name,
                                    visual_type=visual_type,
                                    object_name=object_name,
                                    property_name=property_name,
                                    visual_value=str(visual_value),
                                    theme_value=str(theme_value),
                                    is_match=is_match,
                                    _objects_key=objects_key,
                                    _entry_idx=entry_idx,
                                )
                            )
                            visual_has_override = True

            if visual_has_override:
                result.visuals_with_overrides += 1

    return result


def fix_theme_overrides(
    project: Project,
    result: ThemeAuditResult,
    *,
    dry_run: bool = False,
) -> int:
    """Remove per-visual properties that match the theme defaults."""
    removals: dict[str, list[ThemeOverrideEntry]] = {}
    for entry in result.overrides:
        if not entry.is_match:
            continue
        key = f"{entry.page_name}/{entry.visual_name}"
        removals.setdefault(key, []).append(entry)

    if dry_run or not removals:
        return result.redundant_count

    removed = 0
    for page in project.get_pages():
        for visual in project.get_visuals(page):
            if "visualGroup" in visual.data:
                continue
            key = f"{page.display_name}/{visual.name}"
            entries_to_remove = removals.get(key)
            if not entries_to_remove:
                continue

            changed = False
            for entry in entries_to_remove:
                objects = visual.data.get("visual", {}).get(entry._objects_key, {})
                object_entries = objects.get(entry.object_name)
                if not isinstance(object_entries, list):
                    continue
                if entry._entry_idx >= len(object_entries):
                    continue
                properties = object_entries[entry._entry_idx].get("properties", {})
                if entry.property_name in properties:
                    del properties[entry.property_name]
                    removed += 1
                    changed = True
                if not properties:
                    object_entries[entry._entry_idx].pop("properties", None)
                if not object_entries[entry._entry_idx]:
                    object_entries.pop(entry._entry_idx)
                if not object_entries:
                    objects.pop(entry.object_name, None)

            if changed:
                for objects_key in ("objects", "visualContainerObjects"):
                    object_dict = visual.data.get("visual", {}).get(objects_key, {})
                    if isinstance(object_dict, dict) and not object_dict:
                        visual.data.get("visual", {}).pop(objects_key, None)
                visual.save()

    return removed
