"""Project-scoped visual style preset storage and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from pbi.project import Project
from pbi.properties import (
    VISUAL_PROPERTIES,
    get_property,
    normalize_property_name,
    set_property,
)
from pbi.roundtrip import iter_nested_property_assignments


@dataclass(frozen=True)
class StylePreset:
    """A saved visual style preset."""

    name: str
    path: Path
    properties: dict[str, Any]
    description: str | None = None


def create_style(
    project: Project,
    style_name: str,
    properties: Mapping[str, Any],
    *,
    description: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Create a style preset file under .pbi-styles/."""
    if not properties:
        raise ValueError("Style must include at least one property.")

    path = _style_path(project, style_name)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Style "{style_name}" already exists. Use --force to replace it.'
        )

    normalized = _normalize_style_properties(properties)
    payload: dict[str, Any] = {
        "name": _validate_style_name(style_name),
        "properties": normalized,
    }
    if description:
        payload["description"] = description

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    return path


def get_style(project: Project, style_name: str) -> StylePreset:
    """Load and validate one saved style preset."""
    path = _style_path(project, style_name)
    if not path.exists():
        raise FileNotFoundError(f'Style "{style_name}" not found')

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f'Style "{style_name}" is not valid YAML: {e}') from e

    if not isinstance(data, dict):
        raise ValueError(f'Style "{style_name}" must be a YAML mapping.')

    raw_name = data.get("name", style_name)
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(f'Style "{style_name}" must have a non-empty string name.')

    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f'Style "{style_name}" description must be a string.')

    raw_properties = data.get("properties")
    if not isinstance(raw_properties, dict) or not raw_properties:
        raise ValueError(f'Style "{style_name}" must define a non-empty properties mapping.')

    return StylePreset(
        name=_validate_style_name(raw_name),
        path=path,
        description=description,
        properties=_normalize_style_properties(raw_properties),
    )


def list_styles(project: Project) -> list[StylePreset]:
    """List all valid saved style presets."""
    styles_dir = _styles_dir(project)
    if not styles_dir.exists():
        return []

    presets: list[StylePreset] = []
    for path in sorted(styles_dir.glob("*.yaml")):
        try:
            presets.append(get_style(project, path.stem))
        except (FileNotFoundError, ValueError):
            continue
    return presets


def delete_style(project: Project, style_name: str) -> bool:
    """Delete a saved style preset."""
    path = _style_path(project, style_name)
    if not path.exists():
        return False
    path.unlink()
    return True


def dump_style(style: StylePreset) -> str:
    """Serialize a style preset as YAML for CLI display."""
    payload: dict[str, Any] = {
        "name": style.name,
        "properties": style.properties,
    }
    if style.description:
        payload["description"] = style.description
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )


def extract_style_properties(visual_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the canonical style-only property map from an exported visual spec."""
    result: dict[str, Any] = {}
    for prop_name, value in iter_nested_property_assignments(
        visual_spec,
        exclude_keys={
            "id",
            "name",
            "type",
            "position",
            "size",
            "bindings",
            "sort",
            "filters",
            "isHidden",
            "pbir",
            "style",
        },
    ):
        result[normalize_property_name(prop_name, VISUAL_PROPERTIES)] = value
    return result


def match_style_preset(project: Project, visual_spec: Mapping[str, Any]) -> StylePreset | None:
    """Return the exact saved style preset for a visual spec, if one exists."""
    visual_properties = extract_style_properties(visual_spec)
    if not visual_properties:
        return None
    for preset in list_styles(project):
        if preset.properties == visual_properties:
            return preset
    return None


def apply_style_reference(
    visual_spec: Mapping[str, Any],
    style_name: str,
) -> dict[str, Any]:
    """Replace explicit style properties with a style reference."""
    stripped = _strip_style_properties(visual_spec)
    result = dict(stripped)
    result["style"] = style_name
    return result


def _styles_dir(project: Project) -> Path:
    return project.root / ".pbi-styles"


def _validate_style_name(style_name: str) -> str:
    if not style_name or style_name in {".", ".."}:
        raise ValueError("Style name must be a non-empty file-safe name.")
    if "/" in style_name or "\\" in style_name:
        raise ValueError("Style name may not contain path separators.")
    if Path(style_name).is_absolute():
        raise ValueError("Style name may not be an absolute path.")
    return style_name


def _style_path(project: Project, style_name: str) -> Path:
    safe_name = _validate_style_name(style_name)
    return _styles_dir(project) / f"{safe_name}.yaml"


def _normalize_style_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_name, raw_value in properties.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("Style property names must be non-empty strings.")
        prop_name = normalize_property_name(raw_name, VISUAL_PROPERTIES)
        scratch: dict[str, Any] = {}
        try:
            set_property(scratch, prop_name, _style_value_to_string(raw_value), VISUAL_PROPERTIES)
        except ValueError as e:
            raise ValueError(f"{raw_name}: {e}") from e
        normalized[prop_name] = get_property(scratch, prop_name, VISUAL_PROPERTIES)
    return normalized


def _style_value_to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise ValueError(
        f"Style property values must be scalar strings, numbers, or booleans, got {type(value).__name__}."
    )


def _strip_style_properties(
    value: Mapping[str, Any],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    """Return an exported visual spec with style properties removed."""
    result: dict[str, Any] = {}
    for key, child in value.items():
        prop_name = key if not prefix else f"{prefix}.{key}"
        if prefix == "" and key in {
            "id",
            "name",
            "type",
            "position",
            "size",
            "bindings",
            "sort",
            "filters",
            "isHidden",
            "pbir",
        }:
            result[key] = child
            continue
        if isinstance(child, Mapping):
            nested = _strip_style_properties(child, prefix=prop_name)
            if nested:
                result[key] = nested
            continue
        if prefix == "":
            continue
        if prop_name.startswith("chart:") or "." in prop_name:
            continue
        result[key] = child
    return result
