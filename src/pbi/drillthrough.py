"""Drillthrough and tooltip page configuration for PBIR reports.

Drillthrough pages accept filter context from source visuals, enabling
detail-level navigation. Tooltip pages provide custom hover overlays.
Both use `type` and `pageBinding` in page.json.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from pbi.project import Page


def configure_drillthrough(
    page: Page,
    fields: list[tuple[str, str, str]],
    *,
    cross_report: bool = False,
    hide: bool = True,
) -> None:
    """Configure a page as a drillthrough target.

    Args:
        page: The page to configure.
        fields: List of (entity, property, field_type) tuples for drillthrough fields.
            field_type is "column" or "measure".
        cross_report: Enable cross-report drillthrough.
        hide: Hide the page in view mode after configuring drillthrough.
    """
    page.data["type"] = "Drillthrough"
    if hide:
        page.data["visibility"] = "HiddenInViewMode"

    binding, filters = build_drillthrough_payload(fields, cross_report=cross_report)
    page.data["pageBinding"] = binding

    # Merge drillthrough filters into existing filterConfig
    filter_config = page.data.setdefault("filterConfig", {})
    existing_filters = filter_config.setdefault("filters", [])
    # Remove old drillthrough filters
    existing_filters[:] = [
        f for f in existing_filters
        if not f.get("name", "").startswith("drillFilter")
    ]
    existing_filters.extend(filters)


def clear_drillthrough(page: Page) -> bool:
    """Remove drillthrough configuration from a page. Returns True if removed."""
    changed = False

    if page.data.get("type") == "Drillthrough":
        page.data.pop("type", None)
        changed = True

    if "pageBinding" in page.data and page.data["pageBinding"].get("type") == "Drillthrough":
        page.data.pop("pageBinding", None)
        changed = True

    # Remove drillthrough filters
    filter_config = page.data.get("filterConfig", {})
    filters = filter_config.get("filters", [])
    new_filters = [f for f in filters if not f.get("name", "").startswith("drillFilter")]
    if len(new_filters) != len(filters):
        filter_config["filters"] = new_filters
        changed = True

    # Restore visibility
    if page.data.get("visibility") == "HiddenInViewMode":
        page.data["visibility"] = "AlwaysVisible"

    return changed


def get_drillthrough_fields(page: Page) -> list[tuple[str, str, str]]:
    """Get drillthrough fields as (entity, property, field_type) tuples."""
    binding = page.data.get("pageBinding", {})
    if binding.get("type") != "Drillthrough":
        return []

    result: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for param in binding.get("parameters", []):
        field = _field_from_field_expr(param.get("fieldExpr", {}))
        if field is not None and field not in seen:
            result.append(field)
            seen.add(field)

    if result:
        return result

    filter_config = page.data.get("filterConfig", {})
    for filter_obj in filter_config.get("filters", []):
        if not isinstance(filter_obj, dict):
            continue
        if not str(filter_obj.get("name", "")).startswith("drillFilter"):
            continue
        field = _field_from_field_expr(filter_obj.get("field", {}))
        if field is not None and field not in seen:
            result.append(field)
            seen.add(field)
    return result


def get_tooltip_fields(page: Page) -> list[tuple[str, str, str]]:
    """Get tooltip auto-match fields as (entity, property, field_type) tuples."""
    binding = page.data.get("pageBinding", {})
    if binding.get("type") != "Tooltip":
        return []

    result: list[tuple[str, str, str]] = []
    for param in binding.get("parameters", []):
        field = _field_from_field_expr(param.get("fieldExpr", {}))
        if field is not None:
            result.append(field)
    return result


def is_cross_report_drillthrough(page: Page) -> bool:
    """Check if a drillthrough page is configured for cross-report use."""
    binding = page.data.get("pageBinding", {})
    return (
        binding.get("type") == "Drillthrough"
        and binding.get("referenceScope") == "CrossReport"
    )


def configure_tooltip_page(
    page: Page,
    fields: list[tuple[str, str, str]] | None = None,
    *,
    width: int = 320,
    height: int = 240,
) -> None:
    """Configure a page as a custom tooltip page.

    Args:
        page: The page to configure.
        fields: Optional list of (entity, property, field_type) for auto-matching.
        width: Tooltip page width (default 320).
        height: Tooltip page height (default 240).
    """
    page.data["type"] = "Tooltip"
    page.data["visibility"] = "HiddenInViewMode"
    page.data["width"] = width
    page.data["height"] = height
    page.data["pageBinding"] = build_tooltip_payload(fields)
    filter_config = page.data.get("filterConfig", {})
    filters = filter_config.get("filters", [])
    if isinstance(filters, list):
        filter_config["filters"] = [
            f for f in filters
            if not str(f.get("name", "")).startswith("drillFilter")
        ]


def clear_tooltip_page(page: Page) -> bool:
    """Remove tooltip configuration from a page. Returns True if removed.

    Restores default report page size (1280x720) since tooltip pages
    use a small size (e.g. 320x240) that would be wrong for a normal page.
    """
    changed = False

    if page.data.get("type") == "Tooltip":
        page.data.pop("type", None)
        changed = True

    if "pageBinding" in page.data and page.data["pageBinding"].get("type") == "Tooltip":
        page.data.pop("pageBinding", None)
        changed = True

    if page.data.get("visibility") == "HiddenInViewMode":
        page.data["visibility"] = "AlwaysVisible"

    # Restore default page size if still at tooltip dimensions
    if changed and page.data.get("width", 0) <= 400 and page.data.get("height", 0) <= 300:
        page.data["width"] = 1280
        page.data["height"] = 720

    return changed


def is_drillthrough(page: Page) -> bool:
    """Check if a page is a drillthrough page."""
    return page.data.get("type") == "Drillthrough"


def is_tooltip_page(page: Page) -> bool:
    """Check if a page is a tooltip page."""
    return page.data.get("type") == "Tooltip"


def build_drillthrough_payload(
    fields: list[tuple[str, str, str]],
    *,
    cross_report: bool = False,
) -> tuple[dict, list[dict]]:
    """Build canonical drillthrough pageBinding and filter payloads."""
    binding_id = secrets.token_hex(16)
    parameters = []
    filters = []

    for i, (entity, prop, field_type) in enumerate(fields):
        filter_name = f"drillFilter{i}"
        field_key = "Column" if field_type == "column" else "Measure"

        parameters.append({
            "name": f"param{i}",
            "boundFilter": filter_name,
            "fieldExpr": {
                field_key: {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop,
                },
            },
        })

        filters.append({
            "name": filter_name,
            "field": {
                field_key: {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop,
                },
            },
            "type": "Categorical",
        })

    return {
        "name": binding_id,
        "type": "Drillthrough",
        "referenceScope": "CrossReport" if cross_report else "Default",
        "parameters": parameters,
    }, filters


def build_tooltip_payload(fields: list[tuple[str, str, str]] | None = None) -> dict:
    """Build canonical tooltip pageBinding payload."""
    binding_id = secrets.token_hex(16)
    parameters = []

    if fields:
        for i, (entity, prop, field_type) in enumerate(fields):
            field_key = "Column" if field_type == "column" else "Measure"
            parameters.append({
                "name": f"tooltipParam{i}",
                "fieldExpr": {
                    field_key: {
                        "Expression": {"SourceRef": {"Entity": entity}},
                        "Property": prop,
                    },
                },
            })

    return {
        "name": binding_id,
        "type": "Tooltip",
        "parameters": parameters,
    }


def parse_tooltip_shorthand(
    project_root: Path,
    tooltip_spec: Any,
    *,
    model: Any = None,
) -> list[tuple[str, str, str]]:
    """Parse tooltip shorthand into resolved field tuples."""
    return _parse_binding_field_list(project_root, tooltip_spec, allow_empty=True, model=model)


def parse_drillthrough_shorthand(
    project_root: Path,
    drillthrough_spec: Any,
    *,
    model: Any = None,
) -> tuple[list[tuple[str, str, str]], bool]:
    """Parse drillthrough shorthand into resolved field tuples plus cross-report flag."""
    cross_report = False
    field_spec = drillthrough_spec

    if isinstance(drillthrough_spec, dict):
        allowed_keys = {"fields", "crossReport", "cross-report"}
        unknown = set(drillthrough_spec) - allowed_keys
        if unknown:
            raise ValueError(
                f"drillthrough supports only {', '.join(sorted(allowed_keys))}; got {', '.join(sorted(unknown))}."
            )
        field_spec = drillthrough_spec.get("fields")
        cross_report = bool(
            drillthrough_spec.get("crossReport", drillthrough_spec.get("cross-report", False))
        )

    fields = _parse_binding_field_list(project_root, field_spec, allow_empty=False, model=model)
    if not fields:
        raise ValueError("drillthrough requires at least one field.")
    return fields, cross_report


def _parse_binding_field_list(
    project_root: Path,
    field_spec: Any,
    *,
    allow_empty: bool,
    model: Any = None,
) -> list[tuple[str, str, str]]:
    """Parse one-or-many shorthand field refs into resolved binding tuples."""
    if field_spec in (None, True):
        return [] if allow_empty else []
    if isinstance(field_spec, str):
        refs = [field_spec]
    elif isinstance(field_spec, list) and all(isinstance(item, str) for item in field_spec):
        refs = field_spec
    elif isinstance(field_spec, dict):
        allowed_keys = {"fields"}
        unknown = set(field_spec) - allowed_keys
        if unknown:
            raise ValueError(
                f"tooltip supports only {', '.join(sorted(allowed_keys))}; got {', '.join(sorted(unknown))}."
            )
        return _parse_binding_field_list(
            project_root,
            field_spec.get("fields"),
            allow_empty=allow_empty,
            model=model,
        )
    else:
        kind = type(field_spec).__name__
        raise ValueError(f"field shorthand must be a string, list of strings, or mapping, got {kind}.")

    fields: list[tuple[str, str, str]] = []
    for ref in refs:
        entity, prop, field_type = _resolve_field_ref(project_root, ref, model=model)
        fields.append((entity, prop, field_type))
    return fields


def _resolve_field_ref(
    project_root: Path,
    field_ref: str,
    *,
    model: Any = None,
) -> tuple[str, str, str]:
    """Resolve a shorthand field ref to entity/prop/type."""
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


def _field_from_field_expr(field_expr: dict) -> tuple[str, str, str] | None:
    """Extract one field tuple from a pageBinding/filter field expression."""
    if not isinstance(field_expr, dict):
        return None
    for key, field_type in [("Column", "column"), ("Measure", "measure")]:
        if key not in field_expr:
            continue
        expr = field_expr[key]
        try:
            entity = expr["Expression"]["SourceRef"]["Entity"]
            prop = expr["Property"]
        except (KeyError, TypeError):
            return None
        if not isinstance(entity, str) or not isinstance(prop, str):
            return None
        return entity, prop, field_type
    return None
