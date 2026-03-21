"""Theme-level conditional formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass

from pbi.formatting import ConditionalFormatInfo, parse_conditional_value


@dataclass
class ThemeConditionalFormatInfo:
    """Parsed conditional formatting entry from theme visualStyles."""

    visual_type: str
    role: str
    selector: str
    format: ConditionalFormatInfo


def get_theme_conditional_formats(
    theme_data: dict,
    *,
    visual_type: str | None = None,
    role: str | None = None,
) -> list[ThemeConditionalFormatInfo]:
    """Extract conditional formatting entries from theme visualStyles."""
    results: list[ThemeConditionalFormatInfo] = []
    visual_styles = theme_data.get("visualStyles", {})
    if not isinstance(visual_styles, dict):
        return results

    for vt, roles in visual_styles.items():
        if visual_type is not None and vt != visual_type:
            continue
        if not isinstance(roles, dict):
            continue
        for branch, objects in roles.items():
            if role is not None and branch != role:
                continue
            if not isinstance(objects, dict):
                continue
            for object_name, entries in objects.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    selector_id = entry.get("$id", "")
                    for property_name, raw_value in entry.items():
                        if property_name == "$id":
                            continue
                        info = parse_conditional_value(object_name, property_name, raw_value)
                        if info is None:
                            continue
                        results.append(
                            ThemeConditionalFormatInfo(
                                visual_type=vt,
                                role=branch,
                                selector=selector_id,
                                format=info,
                            )
                        )
    return results
