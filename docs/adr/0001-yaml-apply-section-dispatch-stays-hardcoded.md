# ADR 0001: YAML apply section dispatch stays hard-coded

## Status

Accepted — 2026-05-02

## Context

The YAML Round-Trip apply engine (`src/pbi/apply/engine.py`) and its export
counterpart (`src/pbi/export.py`) dispatch by name to a small set of top-level
YAML sections: `theme`, `report`, `pages`, `bookmarks`. Each top-level section
has its own apply/export pair (`theme_roundtrip.py`, `report_roundtrip.py`,
`apply/pages.py`, `apply/ops.py`).

To a reviewer skimming the engine, this looks like a textbook "shallow seam"
smell: three or four parallel small modules, each glued by hard-coded calls in
the engine. The natural reaction is to propose a `SectionHandler` protocol or
registry where each section registers `apply` / `export` against a shared
shape, and the engine becomes a loop.

We considered that abstraction during a `/improve-codebase-architecture`
grilling session and rejected it.

## Decision

Top-level YAML section dispatch in the apply engine and exporter remains
hard-coded. Section handlers stay as individual modules with no shared
protocol or registry. We co-locate the dispatch under a single named function
on each side (apply, export) so phase ordering is explicit, and we deduplicate
the small `_merge_dict` helper, but we do not introduce a section-handler
abstraction.

## Reasons

1. **Bounded section count.** Plausible future top-level sections are
   `customVisuals` (currently CLI-only, doesn't round-trip) and a possible
   `resourcePackages` / `images` promotion from a sub-key of `report:` to a
   first-class section. Most other candidates (interactions, drillthrough,
   navigation) are naturally per-page or per-visual, not top-level. Total
   expected lifetime growth: 1–2 new sections, not 5+. The locality win of a
   registry doesn't pay back its indirection cost at that scale.

2. **Sections are already independent.** `pbi apply` is routinely used for
   partial patches (e.g. updating a few visuals on one page without a full
   export). Each section therefore must already be optional, idempotent, and
   safe-when-empty — the existing `if X is not None` checks encode this. A
   registry would re-encode the same property at the protocol level without
   adding enforcement.

3. **Section asymmetries resist a useful protocol.** The four current sections
   differ in load-bearing ways: phase ordering (`bookmarks` runs after pages
   and a `_finalize_visual_page_refs` step; `theme`/`report` run first),
   page-filter respect (`theme`/`report` skip when `--page` is set; `pages`
   does not), result accounting (`theme`/`report` count "top-level keys
   touched"; `pages` counts visuals/properties), and write substrate
   (`theme_roundtrip` calls `apply_theme()` for first-time creation but
   `save_theme_data` otherwise). A protocol loose enough to encode every
   quirk wouldn't constrain anything; a tight protocol would force sections to
   conform at the cost of correctness.

4. **Bugs don't live on the dispatch path.** Bugs in this codebase
   concentrate in *wrong values written into PBIR* — inside each section's
   apply logic, not in section selection. A registry doesn't reduce the bug
   surface; it only redistributes the dispatch wiring.

## Consequences

- Adding a new top-level YAML section requires editing two places: the
  co-located dispatch function in `apply/engine.py` and its mirror in
  `export.py`. This is intentional — the section list is small enough that
  having it visible at both sites is a feature, not a tax.
- A future architecture review that surveys "parallel small modules with
  hard-coded dispatch" will likely re-propose the registry abstraction. This
  ADR is the load-bearing reason to point at.
- This ADR is scoped to **report-side** YAML apply/export only. The
  `model_apply` engine (`pbi model apply`, `src/pbi/model_apply.py`) has its
  own internal dispatch boilerplate over ~10 sections and a separately
  diverged result/rollback/validation shape. Whether the model engine should
  be deepened, and whether report-side and model-side apply should converge
  on a shared engine, is a separate design question.
