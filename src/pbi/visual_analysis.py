"""Runtime access to richer visual capability analysis extracted from Desktop."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _load_analysis() -> dict:
    """Load normalized visual capability analysis.

    Prefer a packaged data file when available; fall back to the generated
    schema-analysis artifact in a source checkout.
    """
    try:
        ref = resources.files("pbi.data").joinpath("visual_capabilities_analysis.json")
        if ref.is_file():
            return json.loads(ref.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass

    generated = Path(__file__).resolve().parents[2] / "schema-analysis" / "generated" / "visual-capabilities.analysis.json"
    if generated.exists():
        return json.loads(generated.read_text(encoding="utf-8"))
    return {"visuals": {}}


def get_visual_analysis(visual_type: str) -> dict[str, Any] | None:
    return _load_analysis().get("visuals", {}).get(visual_type)


def get_visual_analysis_roles(visual_type: str) -> list[dict[str, Any]]:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return []
    return list(visual.get("dataRoles", []))


def get_visual_analysis_role(visual_type: str, role_name: str) -> dict[str, Any] | None:
    role_lower = role_name.lower()
    for role in get_visual_analysis_roles(visual_type):
        if str(role.get("name", "")).lower() == role_lower:
            return role
    return None


def get_visual_analysis_mappings(visual_type: str) -> list[dict[str, Any]]:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return []
    return list(visual.get("dataViewMappings", []))


def get_visual_behavior(visual_type: str) -> dict[str, Any]:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return {}
    return dict(visual.get("behavior", {}))


def supports_sorting(visual_type: str) -> bool | None:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return None
    return "sorting" in visual.get("behavior", {})


def supports_visual_actions(visual_type: str) -> bool | None:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return None
    return visual.get("behavior", {}).get("supportsVisualLink") is True


def supports_tooltips(visual_type: str) -> bool | None:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return None
    return "tooltips" in visual.get("behavior", {})


def supports_on_object_formatting(visual_type: str) -> bool | None:
    visual = get_visual_analysis(visual_type)
    if not visual:
        return None
    return visual.get("behavior", {}).get("supportsOnObjectFormatting") is True


def describe_behavior_features(visual_type: str) -> list[str]:
    behavior = get_visual_behavior(visual_type)
    if not behavior:
        return []

    features: list[str] = []
    if "sorting" in behavior:
        features.append("sorting")
    if "tooltips" in behavior:
        supported_types = behavior.get("tooltips", {}).get("supportedTypes", {})
        if isinstance(supported_types, dict):
            enabled = [name for name, value in supported_types.items() if value]
            if enabled and set(enabled) != {"default"}:
                features.append(f'tooltips ({", ".join(enabled)})')
            else:
                features.append("tooltips")
        else:
            features.append("tooltips")

    drilldown_roles = behavior.get("drilldown", {}).get("roles", [])
    if drilldown_roles:
        features.append(f'drilldown ({", ".join(drilldown_roles)})')

    if behavior.get("supportsVisualLink") is True:
        features.append("visual actions")
    if behavior.get("supportsOnObjectFormatting") is True:
        features.append("on-object formatting")

    return features


def role_max_occurs(visual_type: str, role_name: str) -> int | None:
    """Return the strongest known max cardinality for a role, when inferable."""
    role_lower = role_name.lower()
    max_values: list[int] = []
    for mapping in get_visual_analysis_mappings(visual_type):
        for condition_set in mapping.get("conditionSets", []):
            for constraint in condition_set:
                if str(constraint.get("role", "")).lower() == role_lower:
                    if isinstance(constraint.get("max"), int):
                        max_values.append(constraint["max"])
    if not max_values:
        return None
    return min(max_values)


def role_accepts_multiple(visual_type: str, role_name: str) -> bool:
    role = get_visual_analysis_role(visual_type, role_name)
    if role and role.get("kind") == 1:
        max_occurs = role_max_occurs(visual_type, role_name)
        return max_occurs is None or max_occurs > 1

    max_occurs = role_max_occurs(visual_type, role_name)
    return max_occurs is None or max_occurs > 1


def allowed_role_names(visual_type: str) -> set[str]:
    return {str(role.get("name")) for role in get_visual_analysis_roles(visual_type) if role.get("name")}


def normalize_semantic_data_type(field_type: str, data_type: str | None) -> set[str]:
    """Map CLI/model field metadata to Desktop role type families."""
    normalized = (data_type or "").strip().lower()
    out: set[str] = set()

    if field_type == "measure":
        out.add("numeric")
        out.add("integer")

    if normalized in {"int", "int64", "int32", "whole number", "whole", "integer"}:
        out.update({"integer", "numeric"})
    elif normalized in {"double", "decimal", "number", "currency", "fixeddecimal"}:
        out.add("numeric")
    elif normalized in {"string", "text"}:
        out.add("text")
    elif normalized in {"bool", "boolean"}:
        out.add("bool")
    elif normalized in {"date", "datetime", "datetimezone", "time"}:
        out.add("dateTime")

    return out


def role_type_warning(visual_type: str, role_name: str, field_type: str, data_type: str | None) -> str | None:
    """Return a human-readable type mismatch warning when clearly invalid."""
    role = get_visual_analysis_role(visual_type, role_name)
    if not role:
        return None

    role_kind = role.get("kind")
    if role_kind == 0 and field_type != "column":
        return f'Role "{role_name}" must use a column, not a {field_type}.'
    if role_kind == 1 and field_type != "measure":
        return f'Role "{role_name}" must use a measure, not a {field_type}.'

    required_types = role.get("requiredTypes") or []
    if not required_types:
        return None

    actual_types = normalize_semantic_data_type(field_type, data_type)
    if not actual_types:
        return None

    allowed_types = {key for entry in required_types for key in entry.get("rawKeys", [])}
    if allowed_types and actual_types.isdisjoint(allowed_types):
        expected = ", ".join(sorted(allowed_types))
        actual = ", ".join(sorted(actual_types))
        return (
            f'Role "{role_name}" expects {expected}, but '
            f"{field_type} {actual or 'unknown'} was provided."
        )
    return None
