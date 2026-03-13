"""Drillthrough and tooltip page configuration for PBIR reports.

Drillthrough pages accept filter context from source visuals, enabling
detail-level navigation. Tooltip pages provide custom hover overlays.
Both use `type` and `pageBinding` in page.json.
"""

from __future__ import annotations

import secrets

from pbi.project import Page


def configure_drillthrough(
    page: Page,
    fields: list[tuple[str, str, str]],
    *,
    cross_report: bool = False,
) -> None:
    """Configure a page as a drillthrough target.

    Args:
        page: The page to configure.
        fields: List of (entity, property, field_type) tuples for drillthrough fields.
            field_type is "column" or "measure".
        cross_report: Enable cross-report drillthrough.
    """
    page.data["type"] = "Drillthrough"
    page.data["visibility"] = "HiddenInViewMode"

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

    page.data["pageBinding"] = {
        "name": binding_id,
        "type": "Drillthrough",
        "referenceScope": "CrossReport" if cross_report else "Default",
        "parameters": parameters,
    }

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

    result = []
    for param in binding.get("parameters", []):
        field_expr = param.get("fieldExpr", {})
        for key, ftype in [("Column", "column"), ("Measure", "measure")]:
            if key in field_expr:
                entity = field_expr[key]["Expression"]["SourceRef"]["Entity"]
                prop = field_expr[key]["Property"]
                result.append((entity, prop, ftype))
    return result


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

    page.data["pageBinding"] = {
        "name": binding_id,
        "type": "Tooltip",
        "parameters": parameters,
    }


def clear_tooltip_page(page: Page) -> bool:
    """Remove tooltip configuration from a page. Returns True if removed."""
    changed = False

    if page.data.get("type") == "Tooltip":
        page.data.pop("type", None)
        changed = True

    if "pageBinding" in page.data and page.data["pageBinding"].get("type") == "Tooltip":
        page.data.pop("pageBinding", None)
        changed = True

    if page.data.get("visibility") == "HiddenInViewMode":
        page.data["visibility"] = "AlwaysVisible"

    return changed


def is_drillthrough(page: Page) -> bool:
    """Check if a page is a drillthrough page."""
    return page.data.get("type") == "Drillthrough"


def is_tooltip_page(page: Page) -> bool:
    """Check if a page is a tooltip page."""
    return page.data.get("type") == "Tooltip"
