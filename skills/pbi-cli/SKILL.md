---
name: pbi-cli
description: "General-purpose guide for the `pbi` CLI tool that edits Power BI PBIP project files — use when you need to understand CLI grammar, discover commands, orient in a project, choose between YAML and imperative workflows, or perform common operations like project validation, page management, visual inspection, catalog asset management, or report metadata. Triggers on: pbi commands, Power BI project, PBIP files, report structure, command help, project setup, page management, visual listing, project overview, CLI usage, catalog, reusable assets, report metadata."
---

# PBI CLI — General Usage Guide

The `pbi` CLI edits Power BI PBIP (PBIR format) project files directly — no Power BI Desktop needed. It targets AI agents that build and manage reports programmatically.

## Command Grammar

All commands follow a consistent pattern:

```
pbi <object> <verb> <target> [key=value...] [--flags]
```

**Objects:** `page`, `visual`, `filter`, `interaction`, `bookmark`, `theme`, `model`, `image`, `nav`, `report`, `catalog`

**Verbs work the same across all objects:**

| Verb | What it does |
|------|-------------|
| `list` | Show all items |
| `get` | Show one item's details (never `show`) |
| `set` | Change properties via key=value args |
| `set-all` | Change properties in bulk |
| `create` | Add new item |
| `delete` | Remove item — prompts unless `--force` (never `remove`) |
| `clear` | Remove configuration (sort, formatting, interactions) |
| `apply` | Apply from YAML |
| `export` | Export to YAML/JSON |
| `copy` | Duplicate an item |
| `rename` | Rename an item |

**Subgroup grammar:** When a feature has variants, use noun subgroups before verbs:
- `page tooltip set`, `page drillthrough clear`
- `model measure create`, `model column set`
- `nav page set`, `nav bookmark set`
- `theme style set`, `theme format set`
- `report annotation get`, `report object set`

## Common Flags

| Flag | Meaning | Available on |
|------|---------|-------------|
| `-p, --project` | Specify project path | Every command |
| `--dry-run` | Preview without writing | All mutating commands |
| `--json` | Machine-readable output | All list commands |
| `--force, -f` | Skip confirmation prompt | All delete commands |
| `--page` | Narrow scope to one page | filter, visual set-all, apply |
| `--all-pages` | Apply across every page | visual set-all, visual column |
| `--raw, -r` | Dump full JSON | get/detail commands |
| `--full` | Complete detail dump | visual get |
| `--name, -n` | Friendly name | create commands |

## Project Orientation

Start every session by understanding the project:

```bash
pbi info                          # quick project summary (tree view)
pbi map                           # full YAML map (pages, visuals, model)
pbi map --pages                   # pages and visuals only
pbi map --model                   # model only
pbi map --page "Overview"        # single page detail
pbi capabilities                  # what the CLI supports vs PBIR spec
```

### Pages

```bash
pbi page list                     # list all pages with sizes and visual counts
pbi page get "Overview"           # page properties
pbi page create "Detail View"     # create new page
pbi page copy "Overview" "Copy"   # duplicate with all visuals
pbi page delete "Draft" --force   # delete
pbi page reorder "Pg1" "Pg2"     # set page order
pbi page set-active "Overview"    # set default open page
```

### Visuals

```bash
pbi visual list "Overview"                # visuals with types and positions
pbi visual get "Overview" chart --full    # full detail
pbi visual create "Overview" barChart --name myChart --title "Revenue"
pbi visual delete "Overview" chart --force
pbi visual types                          # all available visual types
pbi visual types barChart                 # roles for one type
```

## Lookup Resolution

All commands resolve targets flexibly:

1. Exact ID
2. Exact display name (case-insensitive)
3. Partial match (if unique)
4. 1-based index (e.g., `1` for first page)
5. Fuzzy suggestion if no match found
6. Available list fallback

So `pbi page get "over"` works if "Overview" is the only page starting with "over". If ambiguous, you get suggestions.

## When to Use YAML vs Imperative

| Task | Approach |
|------|----------|
| Build a new page | Write YAML + `pbi apply` |
| Restyle a page | `pbi page export` → edit → `pbi apply` |
| Redesign completely | Edit YAML → `pbi apply --overwrite` |
| Tweak 1-2 properties | `pbi visual set` (imperative) |
| Bulk format all visuals | `pbi visual set-all` or `pbi catalog apply style/card-panel` |
| Reuse a page layout | `pbi catalog apply page/dashboard-layout "Page"` |
| Stamp repeated widgets | `pbi catalog apply component/kpi-strip "Page" --row 4` |
| Create from a template visual | `pbi catalog apply visual/bar-chart "Page" --set value=Sales.Revenue` |
| Import from another project | `pbi page import --from-project ...` |

**Rule of thumb:** For any page-level work, start with `pbi page export`. Use imperative commands only for quick one-off tweaks. Use catalog assets for reusable patterns.

## The Apply Workflow

The star feature. Define pages in YAML, apply in one shot.

```bash
pbi page export "Overview" -o overview.yaml   # 1. export
# edit overview.yaml                          # 2. edit
pbi diff overview.yaml                        # 3. review changes
pbi apply overview.yaml --dry-run             # 4. validate
pbi apply overview.yaml                       # 5. apply
pbi validate                                  # 6. verify
```

YAML supports: visuals, bindings, properties, filters, interactions, conditional formatting, sort, KPI cards, textbox content, bookmarks, drillthrough/tooltip pages, styles, themes, and raw PBIR passthrough.

For details on YAML syntax, use the **pbi-visuals** skill. For model YAML, use the **pbi-modeling** skill.

## Report Metadata

```bash
pbi report get                                # report metadata
pbi report get theme                          # specific property
pbi report set theme="custom-theme"
pbi report properties                         # writable properties

# Annotations (key-value metadata on the report)
pbi report annotation list
pbi report annotation get PBI_QueryOrder
pbi report annotation set myKey "value"
pbi report annotation delete myKey --force

# Report-level objects/arrays
pbi report object list
pbi report object get slowDataSourceSettings
pbi report object set slowDataSourceSettings key=value
pbi report object clear slowDataSourceSettings
```

## Model Commands (Quick Reference)

```bash
pbi model table list                          # tables
pbi model table rename OldName NewName        # rename a table
pbi model fields Sales                        # columns + measures
pbi model search "revenue"                    # cross-table search
pbi model measure create Sales "Rev" "SUM(Sales[Revenue])"
pbi model relationship list                   # relationships
pbi model path Sales Products                 # join path
pbi model apply model.yaml                    # bulk model changes
```

For full model capabilities, use the **pbi-modeling** skill.

## Filters

Scope narrows with `--page` and `--visual`:

```bash
pbi filter list                                # report-level
pbi filter list --page "Overview"              # page-level
pbi filter list --page "Overview" --visual chart  # visual-level
pbi filter create Sales.Region --value "North" "South"
pbi filter create Sales.Revenue --min 100 --max 999
pbi filter create Sales.Category --topn 5 --topn-by Facts.Revenue
pbi filter delete Sales.Region --page "Overview"
```

## Navigation & Bookmarks

```bash
pbi nav page set "Overview" button "Detail"        # page navigation
pbi nav bookmark set "Overview" button "Minimal"   # apply bookmark
pbi nav back set "Detail" backButton               # back navigation
pbi nav url set "Overview" link "https://..."       # external URL
pbi nav drillthrough set "Detail" button Sales.Region  # drillthrough action
pbi nav toggle set "Overview" button "View Group"  # bookmark-group toggle
pbi nav tooltip set "Page" chart                   # report-page tooltip
pbi nav action get "Page" button                   # inspect current action
pbi bookmark create "Show North" "Overview" --hide chart2
pbi bookmark list
```

## Catalog — Reusable Assets

The unified catalog manages four kinds of reusable assets (visual, style, component, page) across three scopes (project, global, bundled). Bundled assets ship with the CLI.

```bash
# Browse available assets
pbi catalog list                                    # all assets across all scopes
pbi catalog list --kind visual                      # visual templates only
pbi catalog list --kind style --scope bundled       # bundled styles
pbi catalog get visual/bar-chart                    # view asset YAML

# Create from report state
pbi catalog create style --from-visual "Page" --visual chart --name card-style
pbi catalog create style --name flat border.show=false background.show=false
pbi catalog create visual --from-visual "Page" --visual chart --name my-chart
pbi catalog create component --from-visual "Page" --visual "KPI Group" --name kpi-strip
pbi catalog create page --from-visual "Page" --name dashboard-layout

# Apply assets
pbi catalog apply style/card-style "Page" --visual chart          # style one visual
pbi catalog apply style/card-style "Page" --visual-type barChart  # style all of a type
pbi catalog apply visual/bar-chart "Page" --x 16 --y 200 --set value=Sales.Revenue
pbi catalog apply component/kpi-strip "Page" --x 16 --y 90 --row 4 --gap 12
pbi catalog apply page/dashboard-layout "New Page"

# Manage
pbi catalog clone visual/bar-chart --to-global      # share across projects
pbi catalog register my-chart.yaml --kind visual     # import from file
pbi catalog delete style/old-theme --force
pbi catalog validate                                 # verify all catalog YAML
```

Visual and component templates support `{{ param }}` placeholders resolved at apply-time via `--set key=value`. Components also support `--set-each key=v1,v2,v3` for per-instance values when using `--row`.

## Themes

```bash
pbi theme create "Brand" --accent=#0078D4
pbi theme get
pbi theme set foreground=#111111
pbi theme save "corporate" --global
pbi theme load "corporate"
```

## Images

```bash
pbi image create logo.png         # register image
pbi image list                    # list with sizes
pbi image prune --force           # remove unreferenced
```

## Validation

Run after any structural changes:

```bash
pbi validate                      # structural + schema checks
pbi validate --strict             # also fail on warnings
```

Checks: JSON structure, page order, visual interactions, bookmarks, layout issues (overlaps, out-of-bounds), relationship gaps, schema validation (invalid objects/properties with fuzzy suggestions).

## Preview

```bash
pbi render "Page" -o page.html              # HTML layout mockup
pbi render "Page" -o page.html --screenshot # HTML + PNG
```

Pixel-accurate positions with labeled placeholders for data visuals. Useful for reviewing layouts without opening Power BI.

## Cross-Project Operations

```bash
# Import a page from another project
pbi page import --from-project "/path/to/other" --page "Dashboard" --name "My Dashboard"
pbi page import --from-project "/path/to/other" --page "Intro" --include-resources
```

## Confirmation Pattern

All destructive commands prompt unless `--force/-f`:
```
$ pbi page delete "Draft"
Delete "Draft"? [y/N]:
```

## Output Patterns

- Lists: Rich tables with `--json` option for machine-readable output
- Changes: Shows `property: old → new` diffs
- Errors: `Error: message` then exit code 1
- Empty results: Yellow message with suggested command to create items
- Dry-run: Prefixed with `(dry run)` — no files written
