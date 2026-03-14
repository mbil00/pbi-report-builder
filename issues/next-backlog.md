# Remaining Backlog

Short prioritized backlog for the remaining gaps after the round-trip/apply work.

## P1

### FR-002: Style Presets

Status: not started

Why this is next:
- highest remaining authoring-efficiency feature
- large reduction in repeated YAML and repeated `visual set` calls
- naturally builds on the now-stable canonical property surface

Scope:
- add project-scoped preset storage, likely under `.pbi-styles/`
- add `pbi style create|list|show|delete`
- allow `style:` in `pbi apply` visual specs
- allow multiple styles with ordered override semantics
- keep explicit visual properties higher priority than preset values

Suggested implementation notes:
- use the canonical property names already emitted by export
- reuse the shared round-trip/property flattening layer instead of inventing a second property format
- first version can skip auto-detection of matching presets during export

## P2

### Apply/Page Authoring Shorthand For Tooltip and Drillthrough

Status: round-trip supported, authoring shorthand missing

Why this matters:
- export/apply now preserves `type` and `pageBinding`
- authoring a new tooltip or drillthrough page still requires low-level PBIR-shaped YAML

Scope:
- add a higher-level YAML shorthand such as `tooltip:` / `drillthrough:`
- compile shorthand through the shared round-trip layer into canonical `type` + `pageBinding`
- keep existing low-level `pageBinding` support as an escape hatch

Suggested implementation notes:
- align with the existing imperative helpers in [drillthrough.py](/home/mbil/Projects/pbi-report-builder/src/pbi/drillthrough.py)
- make sure shorthand can express cross-report drillthrough

## P3

### FR-005: Expand `visual diff`

Status: partial

Current gap:
- current `pbi visual diff` is mostly explicit-property diffing
- it does not fully compare bindings, sort, filters, or residual fallback PBIR

Scope:
- compare canonical exported visual specs instead of only the current property map
- include:
  - bindings
  - sort
  - filters
  - canonical properties
  - remaining `pbir` fallback payload

Suggested implementation notes:
- use the shared export/round-trip layer as the comparison source of truth
- avoid diffing raw PBIR first; canonicalize as much as possible before comparison

## P4

### Residual Fallback Shapes

Status: intentionally deferred

Remaining sample-report fallback-heavy cases:
- slicer `syncGroup`
- decomposition tree `expansionStates`
- textbox-specific `general` / `values`
- scorecard-specific objects

Why deferred:
- lower reuse across visuals
- weaker payoff than presets and improved diffing
- current fallback mechanism is already sufficient for round-trip safety

Recommended rule:
- only promote one of these when it becomes a repeated real-world authoring need

## P5

### Optional Export Enhancements

Status: deferred

Candidates:
- export style preset references when a visual exactly matches a known preset
- add a “normalized export” / “minimal export” mode if the current default should stay conservative

Why deferred:
- useful, but not blocking apply usability
- depends on style preset design landing first
