# Capability Matrix

This matrix tracks where the CLI already maps well to PBIR editing, where it is partial, where actions are intentionally blocked pending schema-valid writers, and what is still planned.

Use `pbi capabilities` for the same inventory in the CLI.
Use `pbi capabilities --status blocked` to focus on the highest-value schema gaps.

## Supported

| Area | Current support |
|------|-----------------|
| Project discovery and auditing | `pbi info`, `pbi map` (with `--page`/`--pages`/`--model` filters), `pbi validate` (structure + layout + relationship validation) |

## Partial

| Area | Current support | Main gaps |
|------|-----------------|-----------|
| Pages | CRUD, properties, `set-all` batch updates, reorder, active page, full reusable templates (project + global), drillthrough, tooltip | no page annotations/extensions editor |
| Visual containers and formatting | CRUD, layout, alignment (`visual align`), grouping, style presets (project + global), sort, conditional formatting (imperative + YAML), column config (`--all-pages` bulk rename), `set-all --all-pages --where` conditional bulk updates, visual type conversion in apply, `page-diff` | no schema-aware visual/query recipe builder |
| Semantic model and data binding | model introspection, relationships (`model relationships`, `model path`), field formatting, column visibility, measure/calculated-column CRUD, declarative `model apply` (file or stdin), bind/unbind, bindings list | no higher-level query builder, no field parameter workflow |
| Filters | categorical, include, exclude, tuple, range, Top N, and relative date/time at report/page/visual scope; TopN and range also in YAML apply | no Passthrough examples yet |
| Bookmarks and interactions | bookmark CRUD, interaction CRUD, first-class nav commands (`nav set-page`, `nav set-bookmark`, `nav set-back`, `nav set-url`, `nav clear`), both declarable in YAML apply | no bookmark groups |
| Authoring accelerators | `pbi apply` (styles, interactions, bookmarks, conditionalFormatting, bracket selectors, `chart:` prefix, type conversion, overwrite, stdin), `pbi diff` (file or stdin), page export, full-page templates (project + global), style presets (`--from-visual`, global scope, `clone`) | no report scaffold wizard |
| Themes and report resources | theme list/apply/export/delete/migrate (color replacement across visuals) | no broader resource package management |
| Report-level metadata | `report get`, `report set`, `report properties` for core metadata/settings | no resource package editor, no annotations editor |

## Blocked / Planned

| Area | Status | What is missing |
|------|--------|------------------|
| Filters | blocked | exact PBIR writer for Passthrough |
| Authoring accelerators | planned | report/page starter kits, report scaffold wizard, higher-level automation for creating reports from scratch |

## Recommended build order

1. Build richer filter coverage from real PBIR examples plus schema validation.
2. Expand bookmark support with grouping and richer captured state.
3. Expand `report` commands to resources, annotations, and report objects.
4. Build recipe-driven authoring on top of the lower-level PBIR editors.

## Agent note

For larger changes, prefer the workflow in [Agent Workflows](agent-workflows.md):

- inspect with `pbi info` / `pbi map`
- mutate with schema-backed commands where possible
- use `pbi page export` + `pbi apply` for larger declarative page edits
- finish with `pbi validate`
