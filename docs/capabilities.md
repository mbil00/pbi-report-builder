# Capability Matrix

This matrix tracks where the CLI already maps well to PBIR editing, where it is partial, where actions are intentionally blocked pending schema-valid writers, and what is still planned.

Use `pbi capabilities` for the same inventory in the CLI.
Use `pbi capabilities --status blocked` to focus on the highest-value schema gaps.

## Supported

| Area | Current support |
|------|-----------------|
| Project discovery and auditing | `pbi info`, `pbi map` (with `--page`/`--pages`/`--model` filters), `pbi validate` (structure + layout + relationship validation), `pbi visual tree` (group hierarchy) |

## Partial

| Area | Current support | Main gaps |
|------|-----------------|-----------|
| Pages | CRUD, properties, `set-all` batch updates, reorder, active page, full reusable templates (project + global), cross-project page import (`page import --from-project`), page sections (`page section create/list`), drillthrough/tooltip page authoring and inspection (`page drillthrough get`, `page tooltip get`) | no page annotations/extensions editor |
| Visual containers and formatting | CRUD, layout, alignment (`visual arrange align`), grouping, tree view (`visual tree`), style presets (project + global + bundled shape presets), sort, conditional formatting (imperative + YAML), column config (`--all-pages` bulk rename), `set-all --all-pages --where` conditional bulk updates, visual type conversion in apply, `page-diff`, builder-aware `visual create` with `--bind`, `--preset`, auto-title, and model-aware auto-sort for common chart/table/matrix/card/slicer/pie families | no full recipe catalog for every visual type; advanced aggregation patterns still require lower-level editing |
| Semantic model and data binding | model introspection, model annotation CRUD, relationships (`model relationships`, `model path`), field formatting, column visibility, measure/calculated-column CRUD, hierarchy CRUD, partition CRUD, perspective CRUD, RLS role/member/filter CRUD, declarative `model apply` (file or stdin), model export, bind/unbind, bindings list, semantic-model-driven builder defaults during `visual create` | no field parameter workflow; no advanced query builder for edge-case visual shapes; advanced metadata like cultures/translations still needs lower-level editing |
| Filters | categorical, include, exclude, tuple, range, Top N, and relative date/time at report/page/visual scope; TopN and range also in YAML apply | no Passthrough examples yet |
| Bookmarks and interactions | bookmark CRUD, bookmark groups, richer bookmark state export/apply (`state`, `options`, group metadata), bookmark diff/inspection summaries, interaction CRUD, first-class nav commands (`nav page set`, `nav bookmark set`, `nav back set`, `nav url set`, `nav drillthrough set`, `nav action get`, `nav action clear`, `nav tooltip get`, `nav tooltip set`, `nav tooltip clear`), all declarable in YAML apply | higher-level action/layout recipes are still a follow-up |
| Authoring accelerators | `pbi apply` (styles, interactions, bookmarks, conditionalFormatting, bracket selectors, `chart:` prefix, type conversion, overwrite, stdin), `pbi diff` (file or stdin), page export, full-page templates (project + global), style presets (`--from-visual`, global scope, `clone`, bundled shape presets), reusable components (`component create/apply/apply --row`, parameter substitution), semantic-model-driven visual builders on `visual create` | no report/page scaffold wizard yet |
| Themes and report resources | theme create/get/set/apply/export/delete/migrate, preset save/load/clone, `theme style` role-aware `visualStyles` editing, `theme format` conditional-format defaults, top-level YAML `theme:` export/apply/diff round-trip, image resource management (`image create/list/prune`) | obscure Desktop-exported theme payloads may still need low-level JSON edits |
| Report-level metadata | `report get/set/properties` for schema-backed scalar settings, `report annotation list|get|set|delete`, `report object list|get|set|clear`, `report resource package ...`, `report resource item ...`, `report custom-visual list|get|set|delete`, `report data-source-variables get|set|clear`, plus full-report YAML `report:` export/apply/diff round-trip | specialized helpers can still grow, but core report-level authoring is covered |

## Blocked / Planned

| Area | Status | What is missing |
|------|--------|------------------|
| Filters | blocked | Passthrough, Visual, VisualTopN are internal PBI Desktop types (not user-authorable) |
| Authoring accelerators | planned | report/page starter kits, report scaffold wizard, higher-level automation for creating reports from scratch |

## Recommended build order

1. Filter coverage is now comprehensive — all user-facing filter types and advanced operators are supported.
2. Expand `report` commands to resources, annotations, and report objects.
3. Build recipe-driven authoring on top of the lower-level PBIR editors.
4. Add recipe-level action/layout helpers on top of the completed nav/page-binding surface.

## Agent note

For larger changes, prefer the workflow in [Agent Workflows](agent-workflows.md):

- inspect with `pbi info` / `pbi map`
- mutate with schema-backed commands where possible
- use `pbi page export` + `pbi apply` for larger declarative page edits
- finish with `pbi validate`
