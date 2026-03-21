# Report-Building Roadmap

This roadmap narrows the project goal to one thing:

- make PBIP/PBIR report authoring as complete as practical

It explicitly does **not** try to replace Power BI Desktop for:

- publish/deploy workflows
- refresh, credentials, gateways, or service configuration
- Power Query authoring
- Desktop-only inspection UX

The target is a strong authoring layer that can build and evolve reports, leaving final validation and publishing to the user in Power BI Desktop.

## Success Criteria

The project should eventually be able to:

- build most common report pages from model metadata plus declarative specs
- create and edit common visuals without hand-authoring raw PBIR
- capture the major interaction/state flows used in real reports
- edit report, page, visual, theme, and model metadata that materially affects report authoring
- round-trip real exported PBIP fixtures with high confidence

## Principles

1. New write paths must stay schema-backed or be derived from real exported PBIR.
2. Real-fixture tests are the gate for authoring parity work.
3. Prioritize features that reduce raw PBIR editing, not features that add more low-level escape hatches.
4. Finish the common report-authoring surface before chasing edge-case Desktop parity.

## Phase 1: Visual Builders

Status: completed

This is the biggest authoring gap today. The CLI can mutate visuals well, but creating safe, complete visual queries still relies too much on generic bindings.

### Goal

Add visual-type-specific builders so common visuals can be created from semantic-model fields without hand-tuning PBIR query state.

### Deliverables

- Introduce typed builders for the highest-usage visuals:
  - clustered/stacked bar and column
  - line and combo
  - table and matrix
  - card and KPI-style card
  - slicer
  - donut/pie
- Add builder-aware validation for role combinations and field typing.
- Add sensible default formatting/layout presets for each supported builder.
- Add a safer authoring path on top of `visual create` and `visual bind` rather than requiring raw `apply` for common cases.

### Likely CLI surface

- extend `pbi visual create` with typed role arguments and presets, or
- add a new builder-oriented sub-surface that still compiles down to normal visuals

### Exit Criteria

- a new page with common visuals can be built without raw PBIR edits
- builder output survives `pbi validate`
- builder-created visuals round-trip through `export` and `apply`
- real PBIP fixtures can be recreated or meaningfully extended using builders

### Test Gate

- fixture-backed creation tests for each supported visual family
- golden YAML export/apply round-trip for builder-created visuals
- negative tests for invalid role combinations and unsupported query shapes

### Execution Plan

#### Slice 1: Builder-aware `visual create`

Status: completed

- extend `pbi visual create` to accept repeatable role bindings in one command
- allow initial sort setup during creation
- apply sensible default sizes for common visual types
- validate role combinations strictly for modeled role-backed visuals

This slice keeps the existing command surface and removes the need to do:

1. `visual create`
2. `visual bind`
3. `visual bind`
4. `visual sort set`

for the most common authoring flow.

#### Slice 2: Common visual presets

Status: completed

- add builder presets for:
  - clustered/stacked column and bar
  - line and combo
  - table and matrix
  - slicer
  - card/KPI
- set safer defaults for titles, legends, and common layout choices
- expose preset-aware help and validation

Initial implementation shipped:

- explicit `--preset chart`
- explicit `--preset table`
- explicit `--preset slicer`
- explicit `--preset card`
- donut/pie support inside the chart builder family

Current behavior:

- chart presets hide legends for single-series charts and keep them when a
  `Series` role is bound
- slicer presets hide both the visual header and slicer header
- table presets apply a cleaner default grid layout
- card presets apply basic panel styling

#### Slice 3: Semantic-model-driven helpers

Status: completed

- infer column vs measure roles more reliably from the semantic model
- infer sort defaults for date/category axes
- add typed literal and aggregation helpers where PBIR requires them

Initial implementation shipped:

- automatic ascending sort inference for chart categories and slicer values
  when the bound model column defines `sortByColumn`
- explicit `--sort` still wins
- `--no-auto-sort` disables inference
- auto-titles for the common builder families
- stricter builder role/type validation for common visual families

#### Slice 4: Fixture-backed parity

Status: completed

- create builder tests against real PBIP fixtures
- verify builder-created visuals survive export/diff/apply round-trips
- promote supported builders from “partial” to “supported” only after fixture coverage exists

Completed with:

- builder smoke coverage on copied real PBIP fixtures
- validate/export/apply round-trip coverage for builder-created visuals
- unit coverage for chart, combo, donut, slicer, card, table, and matrix builder paths

## Phase 2: Bookmark And State Parity

Status: completed

Current bookmark support is useful but shallow. Power BI bookmarks matter because they are the main way reports encode guided user state.

### Goal

Expand bookmarks from simple visibility snapshots to full authorable report-state objects.

### Deliverables

- author filters captured by bookmarks
- author sort state captured by bookmarks
- author active projections or role state where PBIR supports it
- preserve and edit grouped-visual behavior
- add bookmark grouping support
- improve bookmark inspection so diffs are understandable

Completed with:

- bookmark group metadata authoring via `bookmark group list/create/delete`
- bookmark list/get now surface group membership plus richer state summaries
- bookmark create/set can merge richer `explorationState` and `options` payloads
- full export/apply round-trip now carries top-level `bookmarks:` entries
- bookmark YAML now supports grouped metadata plus richer `state` and `options`
- `pbi diff` now reports bookmark-level changes
- bookmark apply now updates existing bookmarks in place instead of duplicating them

### Related actions

- strengthen `nav bookmark set` workflows
- support bookmark-driven show/hide patterns cleanly in templates/components

### Exit Criteria

- real bookmark-driven reports can be created and maintained without Desktop rework
- exported bookmark PBIR can be edited and reapplied without lossy state drops

### Test Gate

- real-fixture tests using multi-bookmark navigation flows
- regression tests for bookmark updates preserving unrelated state
- apply/export round-trip coverage for bookmarks with richer state payloads

## Phase 3: Tooltip, Drillthrough, And Action Coverage

Status: completed

Pages and nav are already strong, but the remaining interaction surface still has holes.

### Goal

Make page-to-page behavior authorable enough for full report navigation design.

### Deliverables

- first-class `nav` support for drillthrough actions
- first-class `nav` support for tooltip targeting where PBIR allows it
- richer tooltip page binding coverage
- richer drillthrough binding coverage
- helper flows for common navigation/button setups

Completed with:

- first-class `nav drillthrough set`
- first-class `nav tooltip set` and `nav tooltip clear`
- `page drillthrough get` and `page tooltip get` inspection commands
- richer `page get` binding summaries for tooltip and drillthrough pages
- export/apply remapping for visual page-linked properties (`action.page`,
  `action.drillthrough`, `tooltip.section`) across projects
- real-fixture coverage for drillthrough actions and report-page tooltip wiring

### Exit Criteria

- a multi-page guided report with buttons, drillthrough, tooltips, and bookmarks can be built entirely through the CLI

### Test Gate

- fixture-backed tests for drillthrough pages and tooltip pages
- persisted PBIR assertions for all action types
- real-report import/export/apply tests that preserve action wiring

## Phase 4: Report-Level Authoring

Report-level metadata is still thinner than page/visual authoring.

### Goal

Expose the report objects and metadata that materially affect report behavior and packaging.

### Deliverables

- report annotations editor
- broader `report get/set` coverage for report-level arrays and objects
- report resource package editing beyond basic image registration
- report object inspection and mutation helpers

### Shipped

- `report annotation list|get|set|delete`
- `report object list|get|set|clear` for top-level report arrays/objects
- `report resource package ...` and `report resource item ...`
- `report custom-visual list|get|set|delete` for `organizationCustomVisuals`
- `report data-source-variables get|set|clear`
- full-report YAML `report:` export/apply/diff round-trip for report-level metadata

### Exit Criteria

- users can author report-wide settings and metadata without dropping into raw JSON
- report-level edits no longer feel like a secondary path compared to page/visual editing

### Test Gate

- real-fixture tests for report metadata round-trip
- diff/apply coverage for report-level arrays and resources

### Status

Complete.

## Phase 5: Theme And Style Completeness

Theme support is already valuable, but it is not yet complete enough to treat themes as a primary authoring layer for all report styling.

### Status

Complete. Themes now support nested `visualStyles` values, role-branch editing, theme-level conditional-format defaults, top-level YAML `theme:` export/apply/diff, and real-fixture round-trip coverage.

### Goal

Close the gap between simple theme editing and the fuller `visualStyles` patterns exported by Power BI Desktop.

### Deliverables

- broader support for nested `visualStyles` encoding patterns
- theme-level conditional formatting where PBIR supports it
- better inspection/diff tooling for theme style payloads
- clearer theme-to-visual precedence rules in authoring workflows

### Exit Criteria

- teams can maintain complex report-wide styling mostly in themes instead of per-visual patching

### Test Gate

- real-fixture theme round-trip tests with more complex `visualStyles`
- migration/apply/export coverage for nested theme objects

## Phase 6: Model Features That Affect Authoring

This is not about service administration. It is about model features that directly affect what can be built in reports.

### Status

In progress. Perspectives are now first-class in the semantic-model layer, CLI, and model export/apply round-trip. Remaining work is row-level security, partitions, and broader model-wide metadata.

### Goal

Add first-class model editing for report-relevant semantic features that are currently absent.

### Deliverables

- perspectives
- row-level security definitions
- partitions where needed for PBIP/TMDL completeness
- broader model-level settings and metadata

### Exit Criteria

- report-building flows are not blocked by missing semantic-model metadata editors

### Test Gate

- model export/apply round-trip coverage for each new model feature
- fixture-backed inspection tests using a model-heavy PBIP project

## Cross-Cutting Work

These should advance alongside every phase.

### 1. Real Fixture Expansion

- keep adding real exported PBIP fixtures when new report patterns appear
- use fixture-backed tests before claiming parity on a new authoring surface

### 2. Capability Inventory

- keep [capabilities.md](./capabilities.md) and [src/pbi/capabilities.py](/home/mbil/Projects/pbi-report-builder/src/pbi/capabilities.py) aligned with actual implementation
- distinguish `partial` from `supported` aggressively

### 3. Authoring Abstractions

- prefer typed helpers and builders over direct raw-PBIR writes
- keep `apply` as the escape hatch, not the main ergonomic path

### 4. Validation And Diff

- every new authoring feature should land with:
  - validation hooks where possible
  - `get` or inspection visibility
  - export/apply round-trip coverage

## Recommended Build Order

1. Visual builders
2. Bookmark/state parity
3. Tooltip/drillthrough/action coverage
4. Report-level authoring
5. Theme/style completeness
6. Model features that affect report authoring

## What “Complete Enough” Looks Like

The project does not need to match every Desktop pane. It needs to let a user:

- start from a PBIP project and semantic model
- generate pages and common visuals
- wire navigation, bookmarks, drillthrough, and tooltips
- apply consistent styling and themes
- export, diff, and reapply the result safely
- open the project in Power BI Desktop for final inspection rather than core construction
