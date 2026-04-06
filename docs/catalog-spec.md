# Catalog Spec

Unified reusable asset catalog for PBIP authoring.

## Goal

Replace scattered reusable-asset workflows (`style`, `component`, `page template`, and future reusable YAML assets) with one shared catalog model:

- one browse surface
- one storage model
- one validation model
- fewer top-level commands
- better foundation for built-in reusable authoring assets

This spec focuses first on visual authoring assets, but the design is intended to generalize.

## Non-goals

- preserving the current reusable-asset command surface long-term
- a full migration of every existing asset kind in one step
- pixel-perfect visual preview
- replacing `pbi apply` or the existing PBIR authoring engine

## Core Concepts

Every reusable asset is a catalog item.

Each item has:

- `kind` — the execution model and payload shape
- `scope` — where it is stored and whether it is mutable
- `name` — stable identifier within its kind
- `payload` — the reusable YAML body
- metadata used for browsing and validation

### Kinds

Initial kinds:

- `visual`
- `component`
- `page`
- `style`

Planned future kinds:

- `theme-preset`
- `bookmark-pattern`
- `nav-pattern`

### Scopes

- `bundled` — shipped with the installed package, immutable via CLI
- `global` — machine-level, under `~/.config/pbi/`
- `project` — project-local, under the PBIP repo

Resolution order when searching by name without an explicit scope:

1. project
2. global
3. bundled

## Catalog Item Envelope

New catalog items should use a shared envelope:

```yaml
kind: visual
name: hero-kpi-card
category: kpi
description: Large KPI card with title and optional subtitle
tags: [kpi, card, summary]
parameters:
  title:
    type: string
    default: Revenue
payload:
  type: cardVisual
  size: 260 x 120
  title:
    show: true
    text: "{{ title }}"
  bindings:
    Value: "{{ value }}"
```

Envelope fields:

- `kind` — required
- `name` — required
- `category` — optional browse taxonomy
- `description` — optional
- `tags` — optional list of strings
- `parameters` — optional kind-specific parameters
- `payload` — required kind-specific body

## Existing Asset Migration

Existing stored assets do not currently share one envelope.

Current state:

- styles: `.pbi-styles/`, `~/.config/pbi/styles/`, bundled package presets
- components: `.pbi-components/`, `~/.config/pbi/components/`
- page templates: `.pbi-templates/`, `~/.config/pbi/templates/`

Migration strategy:

1. Introduce a shared catalog backend that can read current assets through kind handlers.
2. Add a new catalog CLI surface for browse/get/validate.
3. Add new asset creation/registration through the catalog for new kinds first, especially `visual`.
4. Port existing kinds to catalog-backed storage once handlers and validation settle.
5. Remove legacy reusable-asset command families after the catalog fully replaces them.

Legacy storage formats may remain readable, but the command surface is now catalog-first.

## Storage Layout

Long-term target layout:

- bundled: package data under `pbi/catalog_assets/<kind>/`
- global: `~/.config/pbi/catalog/<kind>/`
- project: `.pbi-catalog/<kind>/`

Compatibility phase:

- existing kinds may continue reading their current directories until migrated
- new kinds should prefer the catalog layout immediately

## CLI Surface

New top-level surface:

- `pbi catalog list`
- `pbi catalog get <ref>`
- `pbi catalog validate`
- `pbi catalog register <yaml>`
- `pbi catalog clone <ref>`
- `pbi catalog delete <ref>`
- `pbi catalog apply <ref>`

Reference syntax:

- `kind/name`
- plain `name` if unique across the filtered result set

Recommended filters:

- `--kind`
- `--scope`
- `--category`
- `--tag`
- `--json`

Examples:

```bash
pbi catalog list
pbi catalog list --kind visual --category kpi
pbi catalog get style/card-standard
pbi catalog validate
pbi catalog validate --kind component
```

Future examples:

```bash
pbi catalog register ./hero-kpi-card.yaml --scope project
pbi catalog apply visual/hero-kpi-card --page Dashboard --x 40 --y 80
```

## Kind Semantics

Kinds share storage and discovery, but not execution.

### `visual`

Purpose:

- reusable single-visual YAML starters
- strongest immediate gap closer for greenfield visual authoring

Payload shape:

- canonical single visual spec derived from `pbi visual export`
- wrapped in the shared envelope

Execution:

- create one visual on a target page
- apply parameters
- position on page
- optionally bind/override fields

### `component`

Purpose:

- reusable grouped visual widgets

Payload shape:

- current component visual list and parameters

Execution:

- stamp one or more visuals
- optionally group them

### `page`

Purpose:

- reusable full-page YAML specs

Payload shape:

- current apply-compatible page YAML

Execution:

- apply to one target page

### `style`

Purpose:

- reusable formatting property bundles

Payload shape:

- current style property mapping

Execution:

- apply to one or more visuals
- or reference from YAML

## Validation Model

Validation should be lightweight and layered.

### 1. YAML validation

- file parses as YAML
- top-level is a mapping

### 2. Envelope validation

For catalog-native items:

- `kind` is present and known
- `name` is a valid file-safe name
- optional metadata types are correct
- `payload` exists

### 3. Kind validation

- `style`: non-empty properties mapping
- `component`: non-empty visuals list
- `page`: exactly one page spec where required by the applying workflow
- `visual`: exactly one visual payload

### 4. Category validation

Category validation should be conservative.

Examples:

- `category=slicer` should reject clearly non-slicer visual types
- `category=table` should accept `tableEx` and `pivotTable`
- `category=kpi` may accept a curated allowlist

Only fail on clear mismatch. Unknown categories should remain possible.

### 5. Deep validation

Optional and project-aware when possible:

- validate property names against the visual property/schema layer
- validate bindings shape
- validate apply-compatible payload structure
- validate field refs against a semantic model if a project is supplied

Deep validation should reuse existing PBIR and schema-backed helpers instead of introducing a second authoring engine.

## Catalog Backend

The backend should expose one interface regardless of kind.

Suggested model:

```python
@dataclass(frozen=True)
class CatalogItem:
    kind: str
    name: str
    scope: str
    path: Path | None
    category: str | None
    description: str | None
    tags: tuple[str, ...]
    summary: dict[str, Any]
```

Suggested handler protocol:

```python
class CatalogHandler(Protocol):
    kind: str
    def list_items(self, project: Project | None) -> list[CatalogItem]: ...
    def get_item(self, project: Project | None, name: str, *, scope: str | None = None) -> CatalogItem: ...
    def dump_item(self, project: Project | None, name: str, *, scope: str | None = None) -> str: ...
    def validate_items(self, project: Project | None, *, scope: str | None = None) -> list[CatalogValidationIssue]: ...
```

The first implementation may wrap existing modules directly instead of migrating storage immediately.

## Migration Rules

- bundled assets are immutable through normal `create`, `register`, `delete`, and `edit` flows
- catalog-native assets should be written in the shared envelope
- legacy items can remain readable during migration
- resolution order is always project, then global, then bundled

## Implementation Phases

### Phase 1

- add spec
- add catalog backend
- support list/get/validate for existing `style`, `component`, and `page` assets
- add `pbi catalog` command group

### Phase 2

- add `visual` kind
- add bundled visual templates
- add project/global registration for visual templates
- add `catalog apply` for visual templates

### Phase 3

- route existing reusable-asset storage through catalog handlers
- remove legacy `style`, `component`, and `page template` command families from the CLI

### Phase 4

- add more reusable kinds
- add richer category-aware validation
- add curated built-in asset libraries for visual/page authoring
