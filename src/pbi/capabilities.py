"""Capability inventory for the CLI versus PBIR/Power BI authoring features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from pbi.schema_refs import (
    BOOKMARK_SCHEMA,
    BOOKMARKS_METADATA_SCHEMA,
    PAGE_SCHEMA,
    REPORT_SCHEMA,
    VISUAL_CONTAINER_SCHEMA,
)

CapabilityStatus = Literal["supported", "partial", "blocked", "planned"]


@dataclass(frozen=True)
class Capability:
    domain: str
    feature: str
    status: CapabilityStatus
    commands: tuple[str, ...]
    pbi_support: str
    cli_support: str
    gap: str
    next_step: str
    schema_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        domain="Core",
        feature="Project discovery, map, validation, diff, render",
        status="supported",
        commands=("pbi info", "pbi map", "pbi validate", "pbi diff", "pbi render"),
        pbi_support="PBIR projects can be inspected and edited as file trees.",
        cli_support="Project discovery, hierarchy mapping, schema-backed structural validation, YAML diff preview, and HTML layout rendering are implemented.",
        gap="Render output is a layout mockup, not a pixel-perfect Power BI preview.",
        next_step="Improve render fidelity with chart placeholders and conditional formatting visualization.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Pages",
        feature="Page lifecycle, layout, sections, import, set-all",
        status="supported",
        commands=(
            "pbi page list", "pbi page get", "pbi page set", "pbi page set-all", "pbi page properties",
            "pbi page create", "pbi page copy", "pbi page delete", "pbi page export", "pbi page import",
            "pbi page reorder", "pbi page set-active", "pbi page section create", "pbi page section list",
        ),
        pbi_support="Power BI supports page lifecycle, sizing, visibility, and ordering metadata.",
        cli_support="Full page lifecycle, bulk set-all, cross-project import, section scaffolding, and apply-compatible export are implemented.",
        gap="No duplicate-with-rebind or page-level annotation editors yet.",
        next_step="Add page duplicate-with-rules and report-open-page helpers.",
        schema_refs=(PAGE_SCHEMA,),
    ),
    Capability(
        domain="Pages",
        feature="Tooltip and drillthrough pages",
        status="partial",
        commands=("pbi page tooltip set", "pbi page tooltip clear", "pbi page drillthrough set", "pbi page drillthrough clear"),
        pbi_support="Power BI supports tooltip and drillthrough pages with binding metadata and filter flow.",
        cli_support="Page binding, sizing, hidden-page behavior, and drillthrough filter wiring are implemented.",
        gap="The CLI does not yet cover the full behavioral surface of these page types or every exported binding variant.",
        next_step="Expand page-binding support based on exact binding parameter patterns seen in exported PBIR samples.",
        schema_refs=(PAGE_SCHEMA,),
    ),
    Capability(
        domain="Visuals",
        feature="Visual lifecycle, layout, arrange, grouping, inspection",
        status="supported",
        commands=(
            "pbi visual create", "pbi visual copy", "pbi visual delete", "pbi visual move", "pbi visual resize",
            "pbi visual rename", "pbi visual group", "pbi visual ungroup", "pbi visual types",
            "pbi visual tree", "pbi visual inspect", "pbi visual export",
            "pbi visual get-page", "pbi visual page-diff", "pbi visual diff",
            "pbi visual arrange row", "pbi visual arrange grid", "pbi visual arrange column", "pbi visual arrange align",
        ),
        pbi_support="Power BI supports visual containers, grouping, layout editing, and alignment tools.",
        cli_support="Full visual lifecycle, type-aware scaffolding, grouping, arrangement (row/grid/column/align), tree view, deep inspection, single-visual export, and cross-visual comparison are implemented.",
        gap="No exhaustive per-visual-type formatting defaults yet (e.g., auto-enabling axes/legend).",
        next_step="Add type-specific formatting presets and safer query builders.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Visuals",
        feature="Visual formatting, properties, and schema-backed editing",
        status="supported",
        commands=(
            "pbi visual get", "pbi visual set", "pbi visual set-all", "pbi visual properties", "pbi visual objects",
            "pbi visual format get", "pbi visual format set", "pbi visual format clear", "pbi visual paste-style",
        ),
        pbi_support="Power BI exposes broad formatting objects for visuals and containers.",
        cli_support="Container and chart properties are editable with schema-backed validation, type coercion, auto-resolve, and fuzzy suggestions. Conditional formatting helpers and style copy are included.",
        gap="The extracted schema covers 57 visual types but edge-case objects may still be missing from the capability extraction.",
        next_step="Expand schema extraction coverage and add visual-type-specific format presets.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Data",
        feature="Role bindings, sort, table/matrix column operations",
        status="supported",
        commands=(
            "pbi visual bind", "pbi visual unbind", "pbi visual bindings", "pbi visual column",
            "pbi visual sort get", "pbi visual sort set", "pbi visual sort clear",
        ),
        pbi_support="Power BI supports visual role projections, sorting, and per-column configuration.",
        cli_support="Projection binding, sort subgroup (get/set/clear), column rename, width, and formatting are implemented. Builder-aware visual create supports repeatable role bindings, semantic-model sort inference, auto titles, and preset-backed defaults for common chart/table/matrix/card/slicer/pie families.",
        gap="Advanced aggregation patterns and edge-case query shapes still need deeper builder support.",
        next_step="Expand builders for richer aggregation/query shapes and add field-parameter workflows.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Model",
        feature="Semantic model: tables, columns, measures, relationships, hierarchies, DAX analysis",
        status="supported",
        commands=(
            "pbi model table list", "pbi model table create",
            "pbi model column list", "pbi model column get", "pbi model column set", "pbi model column create",
            "pbi model column edit", "pbi model column delete", "pbi model column rename",
            "pbi model column hide", "pbi model column unhide",
            "pbi model measure list", "pbi model measure get", "pbi model measure set", "pbi model measure create",
            "pbi model measure edit", "pbi model measure delete", "pbi model measure rename",
            "pbi model relationship list", "pbi model relationship create", "pbi model relationship delete", "pbi model relationship set",
            "pbi model hierarchy list", "pbi model hierarchy create", "pbi model hierarchy delete",
            "pbi model fields", "pbi model search", "pbi model path", "pbi model deps", "pbi model check",
            "pbi model export", "pbi model apply",
        ),
        pbi_support="Power BI semantic models expose tables, columns, measures, relationships, hierarchies, and calculated definitions through TMDL.",
        cli_support="Full CRUD for columns, measures, relationships, and hierarchies. Cascading DAX renames, dependency analysis, relationship path finding, model validation, cross-table search, and declarative YAML apply are implemented.",
        gap="Partitions, row-level security, perspectives, and model-wide settings are not yet first-class.",
        next_step="Add partition management, RLS rules, perspectives, and broader model metadata editing.",
        schema_refs=(),
    ),
    Capability(
        domain="Filters",
        feature="Categorical, include, exclude, tuple, range, Top N, and relative date/time filters",
        status="supported",
        commands=("pbi filter list", "pbi filter create", "pbi filter delete"),
        pbi_support="Power BI supports report, page, and visual filter containers.",
        cli_support="Schema-backed categorical, include, exclude, tuple, range, Top N, and relative date/time filter writes are implemented. Time unit codes are validated against the PBI Desktop schema.",
        gap="Literal typing is still heuristic when semantic-model data types are unavailable.",
        next_step="Expand typed literal encoding using semantic model data types when available.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Filters",
        feature="Passthrough, Visual, and VisualTopN filters",
        status="blocked",
        commands=(),
        pbi_support="Power BI creates these filter types internally during interactions (cross-filtering, drill, visual-level Top N).",
        cli_support="These are read-only internal PBI Desktop filter types and are intentionally not authorable.",
        gap="Passthrough filters appear in the filter pane as non-modifiable. Visual and VisualTopN are runtime-only.",
        next_step="No action needed — these are internal PBI Desktop filter types, not user-authorable.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Bookmarks",
        feature="Bookmark create, update, delete, visibility state",
        status="supported",
        commands=(
            "pbi bookmark list", "pbi bookmark get", "pbi bookmark create",
            "pbi bookmark set", "pbi bookmark delete",
            "pbi bookmark group list", "pbi bookmark group create", "pbi bookmark group delete",
        ),
        pbi_support="Power BI bookmarks can capture page, display, data, drill, and formatting state.",
        cli_support="Bookmark lifecycle, visibility state, bookmark-group metadata, richer state export/apply, grouped YAML round-trip, and readable bookmark diff/inspection summaries are implemented with schema-correct metadata.",
        gap="Bookmark state remains payload-oriented for richer shapes; higher-level helpers for specific bookmark state recipes could still improve ergonomics.",
        next_step="Add recipe-level helpers for common bookmark patterns on top of the supported state round-trip.",
        schema_refs=(BOOKMARK_SCHEMA, BOOKMARKS_METADATA_SCHEMA),
    ),
    Capability(
        domain="Themes",
        feature="Theme authoring, presets, inspection, apply, export, delete, color migration",
        status="supported",
        commands=(
            "pbi theme list", "pbi theme create", "pbi theme get", "pbi theme set",
            "pbi theme properties", "pbi theme apply", "pbi theme export",
            "pbi theme delete", "pbi theme migrate",
            "pbi theme save", "pbi theme load",
            "pbi theme preset list", "pbi theme preset get",
            "pbi theme preset delete", "pbi theme preset clone",
            "pbi theme style list", "pbi theme style get",
            "pbi theme style set", "pbi theme style delete",
        ),
        pbi_support="Power BI supports base themes plus custom themes packaged in report resources.",
        cli_support="Full theme authoring from brand colors with auto-cascade, property inspection, editing with cascade control, reusable theme presets (project + global scope), visual style overrides per visual type with schema validation, and color migration across visual properties are implemented.",
        gap="Not all visualStyles encoding patterns (e.g., complex nested objects) are supported yet.",
        next_step="Expand visualStyles support for complex nested object patterns and theme-level conditional formatting.",
        schema_refs=(REPORT_SCHEMA,),
    ),
    Capability(
        domain="Interactions",
        feature="Visual interactions and navigation actions",
        status="supported",
        commands=(
            "pbi interaction list", "pbi interaction set", "pbi interaction clear",
            "pbi nav set-page", "pbi nav set-bookmark", "pbi nav set-back", "pbi nav set-url", "pbi nav clear",
        ),
        pbi_support="Power BI supports interactions, button actions, page nav, bookmarks, drillthrough, and tooltips.",
        cli_support="Interaction edges and dedicated navigation builders for page nav, bookmark toggle, back button, and web URL actions are implemented.",
        gap="Drillthrough action wiring and tooltip target binding are not yet first-class nav commands.",
        next_step="Add nav set-drillthrough and nav set-tooltip for the remaining action types.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Accelerators",
        feature="Declarative YAML, templates, styles, components, layout calculators",
        status="supported",
        commands=(
            "pbi apply", "pbi diff", "pbi page export", "pbi visual export",
            "pbi page template create", "pbi page template apply", "pbi page template list",
            "pbi page template get", "pbi page template clone", "pbi page template delete",
            "pbi style create", "pbi style list", "pbi style get", "pbi style delete", "pbi style apply", "pbi style clone",
            "pbi component create", "pbi component list", "pbi component get", "pbi component apply", "pbi component delete", "pbi component clone",
            "pbi calc row", "pbi calc grid",
            "pbi render",
        ),
        pbi_support="Power BI itself does not expose all authoring accelerators, but PBIR makes them possible as higher-level tooling.",
        cli_support="Declarative YAML apply with diff preview, page/visual export, reusable page templates, visual style presets with apply/clone, reusable visual components with parameterized stamping, layout position calculators, and semantic-model-driven visual builders on visual create are implemented.",
        gap="No page/report scaffold wizard yet.",
        next_step="Add report starter templates, dataset-driven page scaffolds, and opinionated layout generators.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Images",
        feature="Image resource management",
        status="supported",
        commands=("pbi image create", "pbi image list", "pbi image prune"),
        pbi_support="Power BI supports registered image resources for use in visuals and backgrounds.",
        cli_support="Image registration, listing, and pruning of unreferenced resources are implemented.",
        gap="No image resize, format conversion, or bulk import yet.",
        next_step="Add image optimization helpers and bulk import from directory.",
        schema_refs=(REPORT_SCHEMA,),
    ),
    Capability(
        domain="Report",
        feature="Report-level metadata and settings",
        status="partial",
        commands=("pbi report get", "pbi report set", "pbi report properties"),
        pbi_support="PBIR exposes report metadata beyond themes, including settings, resources, and other report-level objects.",
        cli_support="A dedicated report command group covers core report metadata and settings.",
        gap="Resources, annotations, report objects, and several report-level arrays are still not first-class.",
        next_step="Expand report commands to resources, annotations, report objects, and packaging metadata.",
        schema_refs=(REPORT_SCHEMA,),
    ),
)


def list_capabilities(status: CapabilityStatus | None = None) -> list[Capability]:
    """Return the capability matrix, optionally filtered by status."""
    if status is None:
        return list(CAPABILITIES)
    return [cap for cap in CAPABILITIES if cap.status == status]


def get_capabilities(status: CapabilityStatus | None = None) -> list[Capability]:
    """Backward-compatible alias for the capability inventory."""
    return list_capabilities(status)
