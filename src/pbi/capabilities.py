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
        feature="Project discovery, project map, structural validation",
        status="supported",
        commands=("pbi info", "pbi map", "pbi validate"),
        pbi_support="PBIR projects can be inspected and edited as file trees.",
        cli_support="Project discovery, hierarchy mapping, and structural validation are implemented.",
        gap="Validation is still rule-based rather than full JSON-schema execution.",
        next_step="Add full schema-backed validation with local schema resolution.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Pages",
        feature="Page create, copy, delete, layout, visibility, reorder, active page",
        status="supported",
        commands=("pbi page list", "pbi page get", "pbi page set", "pbi page create", "pbi page copy", "pbi page delete", "pbi page export", "pbi page reorder", "pbi page set-active"),
        pbi_support="Power BI supports page lifecycle, sizing, visibility, and ordering metadata.",
        cli_support="Page lifecycle, core page properties, ordering, active page, and apply-compatible page export are implemented.",
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
        feature="Visual create, copy, move, resize, rename, group",
        status="supported",
        commands=("pbi visual create", "pbi visual copy", "pbi visual move", "pbi visual resize", "pbi visual rename", "pbi visual group", "pbi visual ungroup"),
        pbi_support="Power BI supports visual containers, grouping, and layout editing.",
        cli_support="Core visual container lifecycle, grouping, and type-aware role scaffolding are implemented. Visual create pre-initializes queryState roles and supports --title.",
        gap="No exhaustive per-visual-type formatting defaults yet (e.g., auto-enabling axes/legend).",
        next_step="Add type-specific formatting presets and safer query builders.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Visuals",
        feature="Visual formatting and property editing",
        status="partial",
        commands=("pbi visual get", "pbi visual set", "pbi visual set-all", "pbi visual properties", "pbi visual objects", "pbi visual format get", "pbi visual format set", "pbi visual format clear", "pbi visual paste-style"),
        pbi_support="Power BI exposes broad formatting objects for visuals and containers.",
        cli_support="Many container and chart properties are editable, including conditional formatting helpers and style copy.",
        gap="Public formatting schemas are open-ended, so support is incomplete and not exhaustively proven for every object/property.",
        next_step="Build visual-type-specific format presets from real PBIR exemplars and add schema-sample validation.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Data",
        feature="Role bindings, sort, table/matrix column operations",
        status="partial",
        commands=("pbi visual bind", "pbi visual unbind", "pbi visual bindings", "pbi visual sort", "pbi visual column"),
        pbi_support="Power BI supports visual role projections, sorting, and per-column configuration.",
        cli_support="Basic projection binding, sort definition, rename, width, and formatting are implemented.",
        gap="Binding helpers are generic and do not yet cover the full query shape needed for all visual types.",
        next_step="Introduce per-visual query builders driven by semantic model metadata and exported PBIR patterns.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Model",
        feature="Semantic model inspection and mutation",
        status="partial",
        commands=(
            "pbi model tables",
            "pbi model columns",
            "pbi model measures",
            "pbi model fields",
            "pbi model format",
            "pbi model column hide",
            "pbi model column unhide",
            "pbi model column create",
            "pbi model column edit",
            "pbi model column get",
            "pbi model column delete",
            "pbi model measure create",
            "pbi model measure edit",
            "pbi model measure get",
            "pbi model measure delete",
            "pbi model apply",
        ),
        pbi_support="Power BI semantic models expose tables, columns, measures, formatting metadata, and calculated definitions through TMDL.",
        cli_support="The CLI now supports semantic-model inspection, field formatting, column visibility, measure CRUD, calculated-column CRUD, and declarative batch apply.",
        gap="Coverage is focused on common field-level authoring; broader model metadata, relationships, hierarchies, and model-wide settings are not first-class yet.",
        next_step="Expand from field-level editing into relationships, hierarchies, partitions, and additional model metadata.",
        schema_refs=(),
    ),
    Capability(
        domain="Filters",
        feature="Categorical, include, exclude, tuple, range, Top N, and relative date/time filters",
        status="supported",
        commands=("pbi filter list", "pbi filter create", "pbi filter delete"),
        pbi_support="Power BI supports report, page, and visual filter containers.",
        cli_support="Schema-backed categorical, include, exclude, tuple, range, Top N, and relative date/time filter writes are implemented.",
        gap="Literal typing is still heuristic when semantic-model data types are unavailable.",
        next_step="Expand typed literal encoding and add more advanced filter families.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Filters",
        feature="Passthrough filters",
        status="blocked",
        commands=(),
        pbi_support="Power BI supports these filter modes in the product.",
        cli_support="These writes are intentionally blocked because the CLI does not yet have exact schema-backed payloads for them.",
        gap="The CLI does not yet have exact PBIR representations for these advanced filter types.",
        next_step="Capture a canonical PBIR passthrough sample and implement an exact writer from that exported shape.",
        schema_refs=(REPORT_SCHEMA, PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Bookmarks",
        feature="Bookmark create, update, delete, visibility state",
        status="partial",
        commands=("pbi bookmark list", "pbi bookmark get", "pbi bookmark create", "pbi bookmark set", "pbi bookmark delete"),
        pbi_support="Power BI bookmarks can capture page, display, data, drill, and formatting state.",
        cli_support="Basic bookmark lifecycle and visibility state are implemented with schema-correct metadata.",
        gap="Only a narrow subset of bookmark state is currently authorable.",
        next_step="Expand bookmark capture/edit support for filters, sorts, active projections, and grouped visuals.",
        schema_refs=(BOOKMARK_SCHEMA, BOOKMARKS_METADATA_SCHEMA),
    ),
    Capability(
        domain="Themes",
        feature="Custom theme apply/export/delete",
        status="partial",
        commands=("pbi theme list", "pbi theme apply", "pbi theme export", "pbi theme delete"),
        pbi_support="Power BI supports base themes plus custom themes packaged in report resources.",
        cli_support="Custom theme registration is implemented and now normalized to schema-valid resource packages.",
        gap="Theme authoring and report-level resource management are still minimal.",
        next_step="Add theme scaffold/generate/update commands and broader resource package inspection.",
        schema_refs=(REPORT_SCHEMA,),
    ),
    Capability(
        domain="Interactions",
        feature="Visual interactions and action/navigation wiring",
        status="partial",
        commands=("pbi interaction list", "pbi interaction set", "pbi interaction clear", "pbi visual set action.*"),
        pbi_support="Power BI supports interactions, button actions, page nav, bookmarks, drillthrough, and tooltips.",
        cli_support="Interaction edges and several action properties can be edited.",
        gap="No first-class helpers yet for navigation/button experiences beyond raw property setting.",
        next_step="Add action-button builders for bookmark toggles, page navigation, back buttons, and web links.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Accelerators",
        feature="Declarative page workflows, templates, and style presets",
        status="partial",
        commands=("pbi apply", "pbi page export", "pbi page template create", "pbi page template apply", "pbi page template list", "pbi style create", "pbi style list", "pbi style get", "pbi style delete"),
        pbi_support="Power BI itself does not expose all authoring accelerators, but PBIR makes them possible as higher-level tooling.",
        cli_support="Declarative apply, page export, reusable page templates, and saved visual style presets are implemented.",
        gap="There is no guided report scaffolding, visual layout generation, or semantic-model-driven report builder yet.",
        next_step="Add report starter templates, dataset-driven page scaffolds, and opinionated layout generators.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
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
