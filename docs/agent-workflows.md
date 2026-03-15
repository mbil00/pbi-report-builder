# Agent Workflows

Shortest path to reliable PBIR changes. Prefer declarative YAML over imperative commands.

## Choose Your Workflow

| Task | Approach |
|------|----------|
| Build a new page | Write YAML + `pbi apply` |
| Restyle / restructure a page | `pbi page export` → edit YAML → `pbi apply` |
| Redesign a page completely | `pbi page export` → edit YAML → `pbi apply --overwrite` |
| Reuse a standard intro/info/detail page | `pbi page apply-template` |
| Tweak 1-2 properties | `pbi visual set` (imperative) |
| Apply consistent formatting | `pbi style apply` or `style:` in YAML |
| Change a theme's colors everywhere | `pbi theme migrate old.json new.json` |

**Rule of thumb:** For any page-level work, start with `pbi page export`. Use imperative commands only for quick one-off tweaks.

## Discovery (Before You Build)

Understand what exists before writing anything:

```bash
pbi info                              # tree view of pages and visuals
pbi page list                         # page table with sizes and counts
pbi page get "Page Name"              # page properties, background, visual count
pbi visual list "Page Name"           # visual table with positions and types
pbi visual get "Page" visual --full   # everything: props, objects, columns, filters, sort
pbi model tables                      # semantic model tables
pbi model fields TableName            # columns + measures for binding
pbi model relationships               # table relationships (verify cross-table joins)
pbi model path TableA TableB          # relationship chain between two tables
```

For an existing page you want to modify:

```bash
pbi page export "Sales Overview" -o sales.yaml
```

This gives you the complete YAML spec — position, size, styling, bindings, column widths, display names, filters, sort, interactions, and the raw `pbir` block for full fidelity.

## The Apply Workflow (Preferred)

`pbi apply` creates, styles, binds, and positions visuals from a declarative YAML file in a single command.

YAML commands accept stdin as well as file paths. You can use `-` or pipe generated/templated YAML straight into `pbi apply`, `pbi diff`, or `pbi model apply`.

### Export → Edit → Apply

```bash
pbi page export "Sales Overview" -o sales.yaml   # capture current state
# edit sales.yaml (change what you need)
pbi diff sales.yaml                               # preview changes property-by-property
pbi apply sales.yaml --dry-run                    # validate
pbi apply sales.yaml                              # apply
cat sales.yaml | pbi apply --dry-run              # stdin works too
pbi validate                                      # check layout + structure
```

Common YAML edits:
- Reposition/resize visuals (`position` / `size`)
- Change titles, colors, borders (inline properties)
- Swap bindings (field references under `bindings`)
- Add/remove visuals (append to or delete from `visuals` list; use `--overwrite` for deletions)
- Duplicate a visual (copy a YAML block, change the `name`)
- Restyle everything (find-and-replace a color)

### Interactions and Bookmarks in YAML

Instead of running 20+ imperative `pbi interaction set` commands, declare them in the YAML:

```yaml
pages:
- name: Sales Overview
  interactions:
  - source: slicerRegion
    target: revenueChart
    type: DataFilter
  - source: kpiStrip
    target: revenueChart
    type: NoFilter
  visuals: [...]

bookmarks:
- name: Minimal View
  page: Sales Overview
  hide: [detailTable, footnote]
```

### Conditional Formatting in YAML

```yaml
conditionalFormatting:
  dataPoint.fill:
    mode: measure
    source: Measures.ComplianceColor
  values.fontColor:
    mode: gradient
    source: Sales.Revenue
    min: { color: "#FF0000", value: 0 }
    max: { color: "#00FF00", value: 100 }
```

### Filters in YAML

```yaml
filters:
- field: Product.Category
  type: include
  values: [Bikes, Accessories]
- field: Devices.Manufacturer
  type: topN
  count: 15
  by: Measures Table.Total Devices
- field: Sales.Revenue
  type: range
  min: 1000
  max: 50000
```

## Styles (Reusable Formatting)

Styles save formatting as named presets. Use them to keep visuals consistent across pages without repeating property lists.

### Capture a style from an existing visual

```bash
pbi style create card-style --from-visual "Executive Overview" --visual kpiStrip
```

### Apply a style

```bash
# To one visual
pbi style apply "Device Intelligence" kpiStrip --style card-style

# To all visuals of a type on a page
pbi style apply "Device Intelligence" --visual-type cardVisual --style card-style

# In YAML — just reference the style name
- name: kpiStrip
  type: cardVisual
  style: card-style
  bindings: { ... }
```

### Global styles (shared across projects)

```bash
pbi style create card-style ... --global        # save to ~/.config/pbi/styles/
pbi style clone card-style --to-project         # copy global → project
pbi style clone card-style --to-global          # copy project → global
pbi style list                                  # shows both scopes
```

Style resolution: project-scoped styles take priority, global styles are the fallback.

## Page Templates (Reusable Full Pages)

Page templates now store full apply-compatible page YAML, not just stripped layout shells. Use them for intro pages, landing pages, info pages, repeated detail layouts, and other reusable report sections.

```bash
# Save one page as a reusable template
pbi page save-template "Executive Intro" corp-intro --global --description "Shared intro page"

# Discover available templates
pbi page templates
pbi page templates --global
pbi page templates --json
pbi page template-get corp-intro --global

# Reuse a template on a new or existing page
pbi page create "Intro" --from-template corp-intro --template-global
pbi page apply-template "Overview" corp-intro --global
pbi page apply-template "Overview" corp-intro --global --overwrite
```

Template resolution matches styles: project templates win, global templates are the fallback.

Templates can carry:
- page size and page properties
- visuals and bindings
- filters and interactions
- page-local bookmarks

Use `--overwrite` on `page apply-template` when the target page should be reconciled exactly to the template.

## Bulk Operations

```bash
# Set properties across all pages
pbi visual set-all border.show=true border.radius=4 --all-pages --visual-type slicer

# Set properties only where a value matches
pbi visual set-all border.color="#DDD6CC" --all-pages --where border.color="#EDEBE9"

# Rename a column everywhere
pbi visual column "any" "any" DevicesWithPrimaryUser.UPN --rename "User Principal Name" --all-pages

# Migrate all per-visual overrides when changing themes
pbi theme migrate old-theme.json new-theme.json --dry-run
pbi theme migrate old-theme.json new-theme.json
```

## Imperative Commands (Quick Edits)

```bash
pbi visual set "Sales" chart title.text="Q2 Revenue" border.radius=8
pbi visual move "Sales" chart --x 16 --y 200
pbi visual resize "Sales" chart --width 940 --height 400
pbi visual bind "Sales" chart Values Sales.Revenue
pbi visual align "Sales" s1 s2 s3 s4 --distribute horizontal --margin 16
pbi visual align "Sales" chart1 chart2 --align top --match-height
pbi nav set-page "Sales" nextBtn "Details"
pbi nav set-bookmark "Sales" toggleBtn "Minimal View"
```

## Validation

Run after any structural changes:

```bash
pbi validate
```

Checks:
- JSON structure and required fields
- Page order consistency
- Visual interaction references
- Bookmark schema compliance
- **Layout issues** — overlapping visuals, out-of-bounds, zero-size
- **Relationship gaps** — cross-table bindings without a relationship path

## Naming Strategy

Name visuals early (`name:` in YAML or `--name` on create). Friendly names make commands deterministic, exports readable, and applies idempotent.
