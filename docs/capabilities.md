# Capability Matrix

This matrix tracks where the CLI already maps well to PBIR editing, where it is partial, where actions are intentionally blocked pending schema-valid writers, and what is still planned.

Use `pbi capabilities` for the same inventory in the CLI.
Use `pbi capabilities --status blocked` to focus on the highest-value schema gaps.

## Supported

| Area | Current support |
|------|-----------------|
| Project discovery and auditing | `pbi info`, `pbi map`, `pbi validate` |

## Partial

| Area | Current support | Main gaps |
|------|-----------------|-----------|
| Pages | CRUD, properties, templates, drillthrough, tooltip | no reorder command, no active page setter, no page annotations/extensions editor |
| Visual containers and formatting | CRUD, layout, grouping, style, sort, conditional formatting, column config | no schema-aware visual/query recipe builder, no exhaustive per-visual formatting coverage |
| Semantic model and data binding | model introspection, bind/unbind, bindings list | no higher-level query builder, no field parameter workflow |
| Filters | categorical, include, exclude, tuple, range, Top N, and relative date/time filters at report/page/visual scope | no Passthrough examples yet; public support still depends on exact exported shapes |
| Bookmarks and interactions | bookmark CRUD, interaction CRUD | no bookmark groups, no dedicated action/navigation command surface |
| Themes and report resources | theme list/apply/export/remove | no broader resource package management, no theme authoring workflow |
| Report-level metadata | `report get`, `report set`, `report props` for core metadata/settings | no resource package editor, no annotations editor, no report objects editor |

## Blocked / Planned

| Area | Status | What is missing |
|------|--------|------------------|
| Filters | blocked | exact PBIR writer for Passthrough |
| Authoring accelerators | planned | report/page starter kits, report scaffold wizard, higher-level automation for creating reports from scratch |

## Recommended build order

1. Add `pages metadata` commands for page order and active page.
2. Build richer filter coverage from real PBIR examples plus schema validation.
3. Add first-class navigation/action commands instead of relying on low-level property writes.
4. Expand `report` commands to resources, annotations, and report objects.
5. Build recipe-driven authoring on top of the lower-level PBIR editors.

## Agent note

For larger changes, prefer the workflow in [Agent Workflows](agent-workflows.md):

- inspect with `pbi info` / `pbi map`
- mutate with schema-backed commands where possible
- use `pbi page export` + `pbi apply` for larger declarative page edits
- finish with `pbi validate`
