# Agent Workflows

This guide is the shortest path for an agent to make reliable PBIR changes without fighting internal IDs or partial feature coverage.

## Choose Your Workflow

| Task | Recommended approach |
|------|---------------------|
| **Build a new page from scratch** | Write YAML + `pbi apply` |
| **Restyle or restructure a page** | `pbi page export` → edit YAML → `pbi apply` |
| **Add visuals to a page** | `pbi page export` → add visuals to YAML → `pbi apply` |
| **Redesign a page completely** | `pbi page export` → edit YAML → `pbi apply --overwrite` |
| **Change 1-2 properties on a visual** | `pbi visual set` (imperative) |
| **Quick data binding change** | `pbi visual bind` / `pbi visual unbind` |
| **Add/remove filters** | `pbi filter add` / `pbi filter remove` |
| **Bookmark or interaction tweak** | `pbi bookmark` / `pbi interaction` commands |

**Rule of thumb:** For any page-level work, start with `pbi page export` and edit the YAML. Use imperative commands only for quick one-off tweaks to a single visual.

## The Apply Workflow (Preferred)

`pbi apply` creates, styles, binds, and positions visuals from a declarative YAML file in a single command. It is the most efficient way to build or modify pages.

### Building a new page

Write a YAML spec and apply it:

```yaml
# new-page.yaml
version: 1
pages:
- name: Sales Overview
  width: 1920
  height: 1080
  background:
    color: '#F5F5F5'
  visuals:
  - name: slicerRegion
    type: slicer
    position: 16, 8
    size: 308 x 79
    title:
      show: true
      text: Region
      fontSize: 9
    border:
      show: true
      radius: 4
    bindings:
      Values:
      - Sales.Region

  - name: revenueTable
    type: tableEx
    position: 16, 200
    size: 1888 x 500
    title:
      show: true
      text: Revenue by Product
      fontSize: 12
      bold: true
    border:
      show: true
      radius: 10
    shadow:
      show: true
      transparency: 80
    columnHeaders:
      fontColor: '#FFFFFF'
      backColor: '#2E7D8C'
      bold: true
    values:
      fontColor: '#323130'
    grid:
      horizontal: true
      horizontalColor: '#EDEBE9'
      vertical: false
    bindings:
      Values:
      - Products.Name
      - Products.Category
      - Measures.TotalRevenue
```

```bash
pbi apply new-page.yaml --dry-run    # preview changes
pbi apply new-page.yaml              # create the page and visuals
pbi validate                         # verify structural integrity
```

One command creates the page, all visuals, binds data, and applies formatting.

### Modifying an existing page (export → edit → apply)

This is the most common workflow. Export the current page, edit the YAML, and apply it back.

**Step 1 — Export the page:**

```bash
pbi page export "Sales Overview" -o sales.yaml
```

This captures every visual with its position, size, styling, bindings, column widths, display names, filters, sort definitions, and any page tooltip/drillthrough binding metadata. The output is a complete, editable snapshot of the page.

**Step 2 — Edit the YAML:**

The exported YAML is human-readable. Make your changes directly:

```yaml
visuals:
- name: revenueTable
  position: 16, 200          # ← move it
  size: 1888 x 600           # ← make it taller
  title:
    text: Q2 Revenue         # ← change the title
  bindings:
    Values:
    - Products.Name
    - Products.Category
    - Measures.Q2Revenue      # ← swap the measure

# Add a new visual — just append to the list
- name: regionSlicer
  type: slicer
  position: 16, 8
  size: 308 x 79
  title: { show: true, text: Region }
  border: { show: true, radius: 4 }
  bindings:
    Values:
    - Sales.Region
```

Common edits:
- Reposition or resize visuals (change `position` / `size`)
- Change titles, colors, border radius (edit properties inline)
- Swap data bindings (change field references in `bindings`)
- Add new visuals (append to the `visuals` list)
- Remove visuals (delete from the list + use `--overwrite`)
- Duplicate a visual (copy a block, change the `name`)
- Restyle everything (find-and-replace a color across the file)

Binding shorthand supports both the original field-only form and richer entries for renamed/sized fields:

```yaml
bindings:
  Values:
  - Products.Name
  - field: Products.Category
    displayName: Category
    width: 220
  - Measures.TotalRevenue | Revenue | 160
```

**Step 3 — Preview and apply:**

```bash
pbi apply sales.yaml --dry-run     # preview what would change
pbi apply sales.yaml               # apply (additive — only touches visuals in the YAML)
pbi validate                       # verify structural integrity
```

**Step 4 (optional) — Full reconciliation:**

Use `--overwrite` when the YAML should be the single source of truth. Visuals not in the YAML will be removed. A backup is created automatically and rolled back on failure:

```bash
pbi apply sales.yaml --overwrite
```

### Why export → edit → apply is the fastest workflow

| Alternative approach | Calls for a 10-visual page restyle |
|---|---|
| Imperative (`visual set` + `bind` + `column` per visual) | ~80 calls |
| Write YAML from scratch | 1 call, but you write ~100 lines |
| **Export → edit → apply** | **1 export + 1 apply, edit only what changed** |

The export gives you a correct starting point — you don't need to know the YAML format, property names, or binding syntax. Just export, change what you want, and apply.

### Example: restyle a page to match another

A common task: "make the Sign-In page look like the Device Estate page."

```bash
# 1. Export both pages
pbi page export "Device Estate" -o device-estate.yaml
pbi page export "Sign-In & Activity" -o sign-in.yaml

# 2. Copy the styling from device-estate.yaml into sign-in.yaml
#    (border, shadow, padding, columnHeaders, grid properties)
#    The YAML is plain text — copy-paste or find-and-replace works.

# 3. Preview and apply
pbi apply sign-in.yaml --dry-run
pbi apply sign-in.yaml
```

No need to reverse-engineer the reference page's formatting with `visual get` calls — the exported YAML has everything.

### Key behaviors

- **Additive by default** — only visuals and properties in the YAML are touched; existing visuals not in the YAML are left alone
- **Stable IDs** — export includes `id` values so re-apply updates the same visuals instead of creating duplicates
- **Dry-run** — always available to preview changes before writing
- **Overwrite mode** — full reconciliation with automatic backup and rollback on failure
- **Round-trip safe** — exported YAML can be re-applied without modification; bindings, column widths, display names, and page tooltip/drillthrough metadata survive the round-trip

### YAML property reference

The high-level YAML properties map directly to CLI property names:

```yaml
# Container properties (all visual types)
title: { show, text, fontSize, bold, color }
border: { show, radius, width }
shadow: { show, transparency }
padding: { top, bottom, left, right }

# Table properties (tableEx, matrix)
columnHeaders: { fontColor, backColor, fontSize, bold, fontFamily, wordWrap }
values: { fontColor, backColor, fontSize, fontFamily, wordWrap }
grid: { rowPadding, textSize, horizontal, horizontalColor, horizontalWeight, vertical }

# MultiRowCard properties
categoryLabels: { show, fontSize, color }

# Chart properties
legend: { show, position, fontSize }
labels: { show, fontSize, color }
xAxis: { show, title, fontSize }
yAxis: { show, title, fontSize }

# Slicer properties
slicerHeader: { show, fontColor, background, fontSize }

# Action button
action: { show, type }  # type: Back, Bookmark, PageNavigation, WebUrl
```

### The `pbir` block (advanced)

Exported YAML includes a `pbir` block on each visual — this is the raw PBIR JSON payload that preserves everything, including features the high-level properties don't cover (conditional formatting, per-measure selectors, complex object structures).

In most workflows, you don't need to touch the `pbir` block. The high-level properties and bindings handle position, size, styling, and data. The `pbir` block is there for:

- **Full-fidelity round-trip** — export preserves it, apply passes it through, nothing is lost
- **Advanced formatting** — conditional formatting rules, per-measure accent bar colors, gradient stops
- **Selector-heavy objects** — properties that vary by field (e.g. different column widths per column)
- **Unsupported visual types** — the `pbir` block carries any visual through even if the CLI doesn't have named properties for it

When editing exported YAML, prefer changing the high-level properties over modifying the `pbir` block. The high-level fields override the `pbir` payload for: `position`, `size`, `isHidden`, `bindings`, `sort`, and `filters`.

## Imperative Commands (For Quick Edits)

Use these for targeted changes to existing visuals:

```bash
# Change a single property
pbi visual set "Sales" revenueChart title.text="Q2 Revenue"

# Batch properties on one visual
pbi visual set "Sales" revenueChart border.show=true border.radius=8 shadow.show=true

# Apply to all visuals of a type
pbi visual set-all "Sales" --type slicer border.show=true border.radius=4

# Rename a table column
pbi visual column "Sales" revenueTable "Products.Name" --rename "Product" -w 300

# Move and resize
pbi visual move "Sales" revenueChart 16 200
pbi visual resize "Sales" revenueChart 940 400
```

## Naming Strategy

Give visuals friendly names early — either in the YAML (`name:` field) or with `--name` on create:

```bash
pbi visual create "Sales" clusteredColumnChart --name revenueChart
pbi visual rename "Sales" 3 detailTable
```

Why:
- friendly names make all commands deterministic (no ambiguous index/ID lookups)
- export preserves names so YAML stays readable
- templates and apply both key on names for updates vs creates

## Discovery

Before building, understand the report structure and available data:

```bash
pbi info                           # tree view of pages and visuals
pbi map -o report.yaml             # full index with bindings and filters
pbi page list                      # page table with sizes and counts
pbi visual list "Page Name"        # visual table with positions and types
pbi model tables                   # semantic model tables
pbi model columns TableName        # columns in a table
pbi model measures "Measures Table" # available measures
```

For an existing page you want to restyle, export first:

```bash
pbi page export "Sales Overview" -o sales.yaml
```

This gives you the complete YAML spec you can edit and re-apply.

## Filters

```bash
pbi filter add Product.Category --values "Bikes,Accessories" --mode include
pbi filter add Sales.Revenue --min 1000 --max 50000 --locked
pbi filter add Customers.Region --topn 5 --topn-by Sales.TotalRevenue
pbi filter tuple "Product.Color=Red,Product.Size=Large"
pbi filter list --page "Sales"
```

Supported types: categorical, include, exclude, tuple, range, Top N, relative date, relative time.

## Bookmarks and Interactions

```bash
pbi bookmark create "Minimal View" "Sales" --hide detailTable
pbi bookmark update "Minimal View" --show detailTable
pbi interaction set "Sales" regionSlicer revenueChart NoFilter
```

## Drillthrough and Tooltip Pages

```bash
pbi page set-drillthrough "Product Details" Product.Category
pbi page set-tooltip "Sales Tooltip" Product.Category -W 400 -H 300
```

## Templates

Use templates for reusable layout scaffolds (positions + formatting, no data):

```bash
pbi page save-template "Sales Overview" sales-layout
pbi page apply-template "Q2 Sales" sales-layout
pbi page templates              # list available templates
```

Templates preserve layout and formatting but not bindings, sort, or filters.

## Validation

Run after any structural changes:

```bash
pbi validate
```
