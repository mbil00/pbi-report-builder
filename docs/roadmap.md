# Capability Roadmap

This project is moving toward a schema-first PBIR authoring CLI:

1. Match Microsoft’s published PBIR JSON structures exactly.
2. Cover the full practical authoring surface exposed by PBIR.
3. Add higher-level accelerators on top so creating reports is faster than editing PBIR by hand.

Use `pbi capabilities` to inspect the current support matrix.

For the narrowed goal of PBIP authoring completeness, see
[Report-Building Roadmap](report-building-roadmap.md).

## Current Status

- `supported`: schema-backed and usable today
- `partial`: works for a meaningful slice, but not the full Power BI feature surface
- `blocked`: Power BI supports it, but this CLI intentionally refuses to write it until we have an exact PBIR representation
- `planned`: not yet exposed in the CLI

## Priority Order

### 1. Schema-backed expansion

Close the remaining gaps where Power BI supports a feature and PBIR can represent it, but the CLI does not yet emit the exact object structure:

- advanced filters: Passthrough, Visual, and VisualTopN are internal PBI Desktop types (not user-authorable); all user-facing advanced operators are now supported
- deeper bookmark state: filters, sort state, active projections, grouped visuals
- richer page-binding coverage for tooltip and drillthrough
- broader report-level metadata and resource package management

### 2. Visual/query builders

Move beyond generic mutation helpers and add visual-type-specific builders:

- visual scaffolds per visual type
- safer query builders per role layout
- typed literal encoding from semantic model metadata
- exported-PBIR-based presets for common chart shapes

### 3. Authoring accelerators

Build features that are easier than raw Power BI editing:

- report starter templates
- dataset-driven page generators
- visual layout generators
- action-button builders for bookmarks and page navigation
- reusable report patterns

## Engineering Rule

New write paths should only land if at least one of these is true:

- the structure is directly validated against Microsoft’s published schema, or
- the structure is derived from a canonical PBIR sample exported by Power BI and covered by tests

That rule is what keeps “closing the gap” from turning into new malformed JSON.
