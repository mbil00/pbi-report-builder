"""Shared round-trip codec for apply/export YAML surfaces.

This module is the single source of truth for the YAML shapes that need to
survive export -> edit -> apply without drift between the two code paths.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pbi.drillthrough import (
    build_drillthrough_payload,
    build_tooltip_payload,
    parse_drillthrough_shorthand,
    parse_tooltip_shorthand,
)
from pbi.properties import (
    VISUAL_PROPERTIES,
    canonical_object_property_name,
    decode_pbi_value,
    PropertyDef,
)


@dataclass(frozen=True)
class BindingItem:
    """Normalized high-level binding item used by apply/export."""

    field_ref: str
    entity: str
    prop: str
    field_type: str
    display_name: str | None = None
    width: float | None = None


def export_page_roundtrip_fields(page_data: Mapping[str, Any]) -> dict[str, Any]:
    """Extract page-level round-trip metadata for export."""
    result: dict[str, Any] = {}
    if page_data.get("type"):
        result["type"] = page_data["type"]
    if "pageBinding" in page_data:
        result["pageBinding"] = copy.deepcopy(page_data["pageBinding"])
    return result


def apply_page_roundtrip_fields(
    page_data: dict[str, Any],
    page_spec: Mapping[str, Any],
    *,
    project_root: Path,
    dry_run: bool,
    model: Any = None,
) -> int:
    """Apply page-level round-trip metadata from YAML spec to page data."""
    changes = 0
    shorthand = _compile_page_binding_shorthand(page_spec, project_root, model=model)
    if shorthand:
        changes += len(shorthand)
        if dry_run:
            return changes
        page_data["type"] = shorthand["type"]
        page_data["pageBinding"] = copy.deepcopy(shorthand["pageBinding"])
        page_data["visibility"] = "HiddenInViewMode"
        if "filters" in shorthand:
            filter_config = page_data.setdefault("filterConfig", {})
            existing_filters = filter_config.setdefault("filters", [])
            existing_filters[:] = [
                f for f in existing_filters
                if not f.get("name", "").startswith("drillFilter")
            ]
            existing_filters.extend(copy.deepcopy(shorthand["filters"]))
        return changes

    for key in ("type", "pageBinding"):
        if key not in page_spec:
            continue
        changes += 1
        if dry_run:
            continue
        if page_spec[key] is None:
            page_data.pop(key, None)
        else:
            page_data[key] = copy.deepcopy(page_spec[key])
    return changes


def _compile_page_binding_shorthand(
    page_spec: Mapping[str, Any],
    project_root: Path,
    *,
    model: Any = None,
) -> dict[str, Any] | None:
    """Compile tooltip/drillthrough shorthand into canonical page fields."""
    has_tooltip = "tooltip" in page_spec
    has_drillthrough = "drillthrough" in page_spec

    if not has_tooltip and not has_drillthrough:
        return None
    if has_tooltip and has_drillthrough:
        raise ValueError("Use either 'tooltip' or 'drillthrough' on a page, not both.")
    if "type" in page_spec or "pageBinding" in page_spec:
        raise ValueError(
            "Do not combine page shorthand with low-level 'type' or 'pageBinding'; use one form or the other."
        )

    if has_tooltip:
        fields = parse_tooltip_shorthand(project_root, page_spec.get("tooltip"), model=model)
        return {
            "type": "Tooltip",
            "pageBinding": build_tooltip_payload(fields),
            "visibility": "HiddenInViewMode",
        }

    fields, cross_report = parse_drillthrough_shorthand(
        project_root,
        page_spec.get("drillthrough"),
        model=model,
    )
    binding, filters = build_drillthrough_payload(fields, cross_report=cross_report)
    return {
        "type": "Drillthrough",
        "pageBinding": binding,
        "filters": filters,
        "visibility": "HiddenInViewMode",
    }


def export_bindings(visual_data: Mapping[str, Any]) -> dict[str, Any]:
    """Export query projections into concise bindings shorthand."""
    query_state = (
        visual_data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    widths = get_column_widths(visual_data)
    bindings: dict[str, Any] = {}

    for role, config in query_state.items():
        projections = config.get("projections", [])
        if not projections:
            continue

        items: list[Any] = []
        has_rich_item = False
        for projection in projections:
            ref = projection_field_ref(projection)
            if not ref:
                continue

            item: Any = ref
            rich: dict[str, Any] = {"field": ref}
            display_name = projection.get("displayName")
            if display_name:
                rich["displayName"] = display_name
            width = widths.get(projection.get("queryRef", ""))
            if width is not None:
                rich["width"] = int(width) if float(width).is_integer() else width
            if len(rich) > 1:
                item = rich
                has_rich_item = True
            items.append(item)

        if not items:
            continue
        if len(items) == 1:
            bindings[role] = items[0]
        elif has_rich_item:
            bindings[role] = items
        else:
            bindings[role] = items

    return bindings


def parse_binding_items(
    project_root: Path,
    binding_spec: Any,
    *,
    model: Any = None,
) -> list[BindingItem]:
    """Parse one role's binding YAML into normalized binding items."""
    raw_items = binding_spec if isinstance(binding_spec, list) else [binding_spec]
    return [_parse_binding_item(project_root, raw_item, model=model) for raw_item in raw_items]


def _parse_binding_item(project_root: Path, binding_spec: Any, *, model: Any = None) -> BindingItem:
    """Parse a single binding item from string or object syntax."""
    display_name: str | None = None
    width: float | None = None

    if isinstance(binding_spec, dict):
        if "field" not in binding_spec:
            raise ValueError("binding objects must include 'field'")
        field_ref = str(binding_spec["field"]).strip()
        if not field_ref:
            raise ValueError("binding field cannot be empty")
        if "displayName" in binding_spec and binding_spec["displayName"] is not None:
            display_name = str(binding_spec["displayName"])
        if "width" in binding_spec and binding_spec["width"] is not None:
            width = parse_binding_width(binding_spec["width"])
    elif isinstance(binding_spec, str):
        field_ref, display_name, width = parse_binding_string(binding_spec)
    else:
        raise ValueError(f"unsupported binding item type {type(binding_spec).__name__}")

    entity, prop, field_type = resolve_binding_ref(project_root, field_ref, model=model)
    return BindingItem(
        field_ref=field_ref,
        entity=entity,
        prop=prop,
        field_type=field_type,
        display_name=display_name,
        width=width,
    )


def parse_binding_string(value: str) -> tuple[str, str | None, float | None]:
    """Parse string binding shorthand, including pipe-delimited rich syntax."""
    parts = [part.strip() for part in value.split("|")]
    if len(parts) > 3:
        raise ValueError(f"too many '|' segments in binding '{value}'")
    field_ref = parts[0]
    if not field_ref:
        raise ValueError("binding field cannot be empty")
    display_name = parts[1] if len(parts) >= 2 and parts[1] else None
    width = parse_binding_width(parts[2]) if len(parts) == 3 and parts[2] else None
    return field_ref, display_name, width


def parse_binding_width(value: Any) -> float:
    """Parse an optional width value from a binding item."""
    try:
        return float(str(value).strip())
    except ValueError as e:
        raise ValueError(f"invalid width '{value}'") from e


def resolve_binding_ref(
    project_root: Path,
    field_ref: str,
    *,
    model: Any = None,
) -> tuple[str, str, str]:
    """Resolve a shorthand binding field ref to entity/prop/type."""
    is_measure = field_ref.endswith("(measure)")
    clean_ref = field_ref.replace("(measure)", "").strip()
    dot = clean_ref.find(".")
    if dot == -1:
        raise ValueError(f"field must be Table.Field format: {field_ref}")
    entity = clean_ref[:dot]
    prop = clean_ref[dot + 1 :]
    field_type = "measure" if is_measure else "column"

    if not is_measure:
        try:
            loaded_model = model
            if loaded_model is None:
                from pbi.model import SemanticModel

                loaded_model = SemanticModel.load(project_root)
            entity, prop, field_type = loaded_model.resolve_field(clean_ref)
        except (FileNotFoundError, ValueError, TypeError):
            pass

    return entity, prop, field_type


def match_existing_projection(
    existing_projections: list[dict[str, Any]],
    item: BindingItem,
) -> dict[str, Any] | None:
    """Return and remove a matching existing projection, if one exists."""
    target_field = item.field_ref.lower()
    target_query = f"{item.entity}.{item.prop}".lower()
    for index, projection in enumerate(existing_projections):
        existing_field = projection_field_ref(projection)
        existing_query = projection.get("queryRef", "")
        if isinstance(existing_field, str) and existing_field.lower() == target_field:
            return existing_projections.pop(index)
        if isinstance(existing_query, str) and existing_query.lower() == target_query:
            return existing_projections.pop(index)
    return None


def projection_field_ref(projection: Mapping[str, Any]) -> str | None:
    """Return a shorthand field ref for a projection payload."""
    field = projection.get("field", {})
    if "Column" in field:
        data = field["Column"]
        return f'{data["Expression"]["SourceRef"]["Entity"]}.{data["Property"]}'
    if "Measure" in field:
        data = field["Measure"]
        return f'{data["Expression"]["SourceRef"]["Entity"]}.{data["Property"]} (measure)'
    if "Aggregation" in field:
        inner = field["Aggregation"].get("Expression", {})
        for key in ("Column", "Measure"):
            if key in inner:
                data = inner[key]
                ref = f'{data["Expression"]["SourceRef"]["Entity"]}.{data["Property"]}'
                if key == "Measure":
                    ref += " (measure)"
                return ref
    query_ref = projection.get("queryRef")
    if isinstance(query_ref, str) and query_ref:
        return query_ref
    return None


def build_projection(item: BindingItem) -> dict[str, Any]:
    """Build a new projection payload from a normalized binding item."""
    field_key = "Column" if item.field_type == "column" else "Measure"
    projection = {
        "field": {
            field_key: {
                "Expression": {"SourceRef": {"Entity": item.entity}},
                "Property": item.prop,
            }
        },
        "queryRef": f"{item.entity}.{item.prop}",
        "nativeQueryRef": item.prop,
    }
    if item.display_name:
        projection["displayName"] = item.display_name
    return projection


def get_column_widths(visual_data: Mapping[str, Any]) -> dict[str, float]:
    """Read column width overrides keyed by queryRef."""
    objects = visual_data.get("visual", {}).get("objects", {})
    result: dict[str, float] = {}
    for entry in objects.get("columnWidth", []):
        query_ref = entry.get("selector", {}).get("metadata")
        if not query_ref:
            continue
        raw = entry.get("properties", {}).get("value")
        decoded = decode_pbi_value(raw) if raw is not None else None
        if isinstance(decoded, (int, float)):
            result[query_ref] = float(decoded)
    return result


def export_object_properties(
    objects: Mapping[str, Any],
    registry: Mapping[str, PropertyDef],
    *,
    objects_path: str,
    skip_objects: set[str] | None = None,
    root_aliases: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Export object collections into canonical nested YAML properties."""
    result: dict[str, dict[str, Any]] = {}
    skip_objects = skip_objects or set()
    root_aliases = root_aliases or {}

    for obj_key, entries in objects.items():
        if obj_key in skip_objects:
            continue
        if not isinstance(entries, list) or not entries:
            continue

        object_name = root_aliases.get(obj_key, obj_key)
        object_result: dict[str, Any] = {}
        for entry in entries:
            selector = entry.get("selector", {})
            selector_name = selector.get("id") or selector.get("metadata")
            selector_id = selector.get("id")
            for prop_name, raw_value in entry.get("properties", {}).items():
                decoded = decode_pbi_value(raw_value)
                canonical = canonical_object_property_name(
                    obj_key,
                    prop_name,
                    dict(registry),
                    objects_path=objects_path,
                    selector=selector_id,
                )
                # Suppress selector-qualified properties that match known defaults
                # (avoids confusing "cardBorder.show [default]: false" alongside
                # an explicit "border.show: true")
                if selector_name:
                    prop_def = registry.get(canonical)
                    if prop_def and prop_def.default is not None and decoded == prop_def.default:
                        continue
                if canonical.startswith("chart:"):
                    flat_key = canonical
                    if selector_name:
                        flat_key = f"{flat_key} [{selector_name}]"
                    result[flat_key] = decoded
                    continue
                leaf_name = _canonical_leaf_name(
                    object_name,
                    canonical,
                    raw_name=prop_name,
                )
                key = f"{leaf_name} [{selector_name}]" if selector_name else leaf_name
                object_result[key] = decoded

        if object_result:
            result[object_name] = object_result

    return result


def iter_nested_property_assignments(
    spec: Mapping[str, Any],
    *,
    exclude_keys: set[str],
    prefix: str = "",
) -> list[tuple[str, Any]]:
    """Flatten nested YAML dicts into dot-separated property assignments."""
    assignments: list[tuple[str, Any]] = []
    for key, value in spec.items():
        if key in exclude_keys:
            continue
        prop_name = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            assignments.extend(
                iter_nested_property_assignments(
                    value,
                    exclude_keys=set(),
                    prefix=prop_name,
                )
            )
        else:
            assignments.append((prop_name, value))
    return assignments


def prune_visual_pbir(raw_visual: dict[str, Any], exported_visual: Mapping[str, Any]) -> dict[str, Any]:
    """Remove PBIR fragments already represented by the canonical YAML surface."""
    pruned = copy.deepcopy(raw_visual)
    pruned.pop("$schema", None)
    pruned.pop("name", None)
    pruned.pop("position", None)

    visual = pruned.get("visual")
    if isinstance(visual, dict):
        visual.pop("visualType", None)
        if "drillFilterOtherVisuals" in exported_visual:
            visual.pop("drillFilterOtherVisuals", None)

        query = visual.get("query")
        if isinstance(query, dict):
            if "bindings" in exported_visual or _is_empty_mapping(query.get("queryState")):
                query.pop("queryState", None)
            if "sort" in exported_visual or _is_empty_mapping(query.get("sortDefinition")):
                query.pop("sortDefinition", None)
            if not query:
                visual.pop("query", None)

        if "filters" in exported_visual:
            pruned.pop("filterConfig", None)

        objects = visual.get("objects")
        if isinstance(objects, dict):
            if _bindings_have_widths(exported_visual):
                objects.pop("columnWidth", None)
            # Prune textbox paragraphs when text/textStyle shorthand covers them
            if "text" in exported_visual:
                general_entries = objects.get("general")
                if isinstance(general_entries, list):
                    for entry in general_entries:
                        if isinstance(entry, dict):
                            props = entry.get("properties")
                            if isinstance(props, dict):
                                props.pop("paragraphs", None)
                                if not props:
                                    entry.pop("properties", None)
                    objects["general"] = [e for e in general_entries if e]
                    if not objects["general"]:
                        objects.pop("general", None)
            _prune_exported_object_groups(
                objects,
                exported_visual,
                objects_path="objects",
                root_aliases={
                    "categoryAxis": "xAxis",
                    "valueAxis": "yAxis",
                    "lineStyles": "line",
                    "dataPoint": "dataColors",
                },
            )
            if not objects:
                visual.pop("objects", None)

        container_objects = visual.get("visualContainerObjects")
        if isinstance(container_objects, dict):
            _prune_exported_object_groups(
                container_objects,
                exported_visual,
                objects_path="visualContainerObjects",
                root_aliases={
                    "dropShadow": "shadow",
                    "subTitle": "subtitle",
                    "visualHeader": "header",
                    "visualTooltip": "tooltip",
                    "visualLink": "action",
                },
            )
        if _is_empty_mapping(visual.get("visualContainerObjects")):
            visual.pop("visualContainerObjects", None)
        if _is_empty_mapping(visual.get("objects")):
            visual.pop("objects", None)
        if not visual:
            pruned.pop("visual", None)

    if pruned.get("howCreated") == "InsertVisualButton":
        pruned.pop("howCreated", None)

    _normalize_resource_package_types(pruned)
    return _remove_empty_containers(pruned)


def _canonical_leaf_name(object_name: str, canonical: str, *, raw_name: str) -> str:
    """Extract the nested YAML leaf key from a canonical property name."""
    if canonical.startswith("chart:"):
        chart_name = canonical[len("chart:") :]
        prefix = f"{object_name}."
        if chart_name.startswith(prefix):
            return chart_name[len(prefix) :]
        return raw_name
    prefix = f"{object_name}."
    if canonical.startswith(prefix):
        return canonical[len(prefix) :]
    if "." not in canonical:
        return canonical
    return raw_name


def _prune_exported_object_groups(
    objects: dict[str, Any],
    exported_visual: Mapping[str, Any],
    *,
    objects_path: str,
    root_aliases: Mapping[str, str],
) -> None:
    """Drop raw object groups that are fully represented by scalar YAML."""
    for obj_key in list(objects.keys()):
        encoded = export_object_properties(
            {obj_key: objects[obj_key]},
            VISUAL_PROPERTIES,
            objects_path=objects_path,
            root_aliases=root_aliases,
        )
        if not encoded:
            continue
        if _exported_entries_are_scalar(encoded) and _encoded_entries_present(exported_visual, encoded):
            objects.pop(obj_key, None)


def _bindings_have_widths(exported_visual: Mapping[str, Any]) -> bool:
    """Return True when any exported binding includes width metadata."""
    bindings = exported_visual.get("bindings")
    if not isinstance(bindings, Mapping):
        return False
    for value in bindings.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, Mapping) and item.get("width") is not None:
                return True
    return False


def _is_empty_mapping(value: Any) -> bool:
    """Return True when the value is an empty dict-like object."""
    return isinstance(value, Mapping) and not value


def _encoded_entries_present(
    exported_visual: Mapping[str, Any],
    encoded: Mapping[str, Any],
) -> bool:
    """Return True when encoded properties are present in the exported visual."""
    for key, value in encoded.items():
        if isinstance(value, Mapping):
            target = exported_visual.get(key)
            if not isinstance(target, Mapping):
                return False
            for child_key, child_value in value.items():
                if target.get(child_key) != child_value:
                    return False
        else:
            if exported_visual.get(key) != value:
                return False
    return True


def _exported_entries_are_scalar(encoded: Mapping[str, Any]) -> bool:
    """Return True when every exported value is scalar-compatible for apply."""
    for value in encoded.values():
        if isinstance(value, Mapping):
            if any(isinstance(child, (dict, list)) for child in value.values()):
                return False
        elif isinstance(value, list):
            return False
    return True


def _normalize_resource_package_types(data: Any) -> None:
    """Coerce ResourcePackageItem.PackageType floats to int for round-trip parity."""
    if isinstance(data, dict):
        if "ResourcePackageItem" in data:
            rpi = data["ResourcePackageItem"]
            if isinstance(rpi, dict) and "PackageType" in rpi:
                rpi["PackageType"] = int(rpi["PackageType"])
        for value in data.values():
            _normalize_resource_package_types(value)
    elif isinstance(data, list):
        for item in data:
            _normalize_resource_package_types(item)


def _remove_empty_containers(value: Any) -> Any:
    """Recursively remove empty dict/list containers from a JSON-like value."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, child in value.items():
            normalized = _remove_empty_containers(child)
            if normalized in ({}, []):
                continue
            cleaned[key] = normalized
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for child in value:
            normalized = _remove_empty_containers(child)
            if normalized in ({}, []):
                continue
            cleaned_list.append(normalized)
        return cleaned_list
    return value
