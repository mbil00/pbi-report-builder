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
        feature="Page create, copy, delete, layout, visibility",
        status="supported",
        commands=("pbi page list", "pbi page get", "pbi page set", "pbi page create", "pbi page copy", "pbi page delete"),
        pbi_support="Power BI supports page lifecycle, sizing, visibility, and ordering metadata.",
        cli_support="Page lifecycle and core page properties are implemented.",
        gap="Page authoring is property-driven and still lacks broader report-level page operations.",
        next_step="Add page reorder, duplicate-with-rules, and report-open-page helpers.",
        schema_refs=(PAGE_SCHEMA,),
    ),
    Capability(
        domain="Pages",
        feature="Tooltip and drillthrough pages",
        status="partial",
        commands=("pbi page set-tooltip", "pbi page clear-tooltip", "pbi page set-drillthrough", "pbi page clear-drillthrough"),
        pbi_support="Power BI supports tooltip and drillthrough pages with binding metadata and filter flow.",
        cli_support="Basic page binding and visibility wiring exist.",
        gap="The CLI does not yet cover the full behavioral surface of these page types.",
        next_step="Expand page-binding support based on exact binding parameter patterns seen in exported PBIR samples.",
        schema_refs=(PAGE_SCHEMA,),
    ),
    Capability(
        domain="Visuals",
        feature="Visual create, copy, move, resize, rename, group",
        status="supported",
        commands=("pbi visual create", "pbi visual copy", "pbi visual move", "pbi visual resize", "pbi visual rename", "pbi visual group", "pbi visual ungroup"),
        pbi_support="Power BI supports visual containers, grouping, and layout editing.",
        cli_support="Core visual container lifecycle and grouping are implemented.",
        gap="Creation is still generic; it does not scaffold each visual type with Power BI-equivalent defaults.",
        next_step="Add type-specific visual templates and safer visual-type builders.",
        schema_refs=(VISUAL_CONTAINER_SCHEMA,),
    ),
    Capability(
        domain="Visuals",
        feature="Visual formatting and property editing",
        status="partial",
        commands=("pbi visual get", "pbi visual set", "pbi visual set-all", "pbi visual format", "pbi visual paste-style"),
        pbi_support="Power BI exposes broad formatting objects for visuals and containers.",
        cli_support="Many container and chart properties are editable, including conditional formatting helpers.",
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
        domain="Filters",
        feature="Categorical, include, exclude, tuple, range, Top N, and relative date/time filters",
        status="supported",
        commands=("pbi filter list", "pbi filter add", "pbi filter tuple", "pbi filter remove"),
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
        commands=("pbi bookmark list", "pbi bookmark show", "pbi bookmark create", "pbi bookmark update", "pbi bookmark delete"),
        pbi_support="Power BI bookmarks can capture page, display, data, drill, and formatting state.",
        cli_support="Basic bookmark lifecycle and visibility state are implemented with schema-correct metadata.",
        gap="Only a narrow subset of bookmark state is currently authorable.",
        next_step="Expand bookmark capture/edit support for filters, sorts, active projections, and grouped visuals.",
        schema_refs=(BOOKMARK_SCHEMA, BOOKMARKS_METADATA_SCHEMA),
    ),
    Capability(
        domain="Themes",
        feature="Custom theme apply/export/remove",
        status="partial",
        commands=("pbi theme list", "pbi theme apply", "pbi theme export", "pbi theme remove"),
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
        commands=("pbi interaction list", "pbi interaction set", "pbi interaction remove", "pbi visual set action.*"),
        pbi_support="Power BI supports interactions, button actions, page nav, bookmarks, drillthrough, and tooltips.",
        cli_support="Interaction edges and several action properties can be edited.",
        gap="No first-class helpers yet for navigation/button experiences beyond raw property setting.",
        next_step="Add action-button builders for bookmark toggles, page navigation, back buttons, and web links.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Accelerators",
        feature="Templates and report generation helpers",
        status="partial",
        commands=("pbi page save-template", "pbi page apply-template"),
        pbi_support="Power BI itself does not expose all authoring accelerators, but PBIR makes them possible as higher-level tooling.",
        cli_support="Page templates exist as a first accelerator layer.",
        gap="There is no guided report scaffolding, visual layout generation, or semantic-model-driven report builder yet.",
        next_step="Add report starter templates, dataset-driven page scaffolds, and opinionated layout generators.",
        schema_refs=(PAGE_SCHEMA, VISUAL_CONTAINER_SCHEMA),
    ),
    Capability(
        domain="Report",
        feature="Report-level metadata, settings, resources, and packaging",
        status="partial",
        commands=("pbi report get", "pbi report set", "pbi report props"),
        pbi_support="PBIR exposes report metadata beyond themes, including settings and resource packages.",
        cli_support="A first dedicated report command group now covers core report metadata and settings.",
        gap="Resource packages, annotations, report objects, and several report-level arrays are still not first-class.",
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
