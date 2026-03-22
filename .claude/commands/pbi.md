# Power BI Report Development

You are working on a Power BI PBIP project using the `pbi` CLI tool. This tool edits PBIR project files directly — no Power BI Desktop needed. Your goal is to build, style, and lay out report pages that look professional and work correctly.

## Workflow Priority

**Always prefer the declarative YAML approach** — it's faster, produces fewer errors, and handles multiple changes atomically.

1. **Declarative (preferred):** Write/edit YAML, then `pbi apply`
2. **Imperative (for quick tweaks):** `pbi visual set`, `pbi page set`, etc.

## Step 1: Discover What Exists

Before making any changes, understand the current state:

```bash
pbi map                                   # full project overview as YAML
pbi page list                             # pages with sizes and visual counts
pbi visual list "PageName"               # visuals with types and positions
pbi visual get "Page" visual --full       # full detail on one visual
pbi model fields TableName                # available columns + measures for binding
pbi model relationship list               # table relationships
```

For an existing page you want to modify:

```bash
pbi page export "Page Name" -o page.yaml  # capture current state as YAML
```

## Step 2: Build or Edit with YAML

### The apply workflow

```bash
# New page: write YAML from scratch
# Existing page: export first, then edit
pbi page export "Sales" -o sales.yaml

# Preview what would change
pbi diff sales.yaml

# Validate without writing
pbi apply sales.yaml --dry-run

# Apply
pbi apply sales.yaml

# Verify structure
pbi validate
```

### YAML spec reference

```yaml
# Top-level structure
theme:
  name: my-theme
  colors: { ... }

report:
  # report-level metadata (annotations, settings)

pages:
- name: Sales Overview       # page display name (required)
  width: 1280                # default 1280
  height: 720                # default 720

  visuals:
  - name: slicerRegion       # give every visual a name (critical for idempotency)
    type: slicer              # visual type (slicer, cardVisual, barChart, tableEx, etc.)
    position: 16, 8           # x, y
    size: 300 x 65            # width x height
    style: card-panel         # apply a saved style preset

    # Container properties
    title: { show: true, text: Region, fontSize: 10 }
    background: { show: true, color: "#FFFFFF", transparency: 0 }
    border: { show: true, color: "#E2E2E2", radius: 8 }
    shadow: { show: true }

    # Slicer-specific
    slicerHeader: { show: false }
    header: { show: false }

    # Chart properties (prefix chart: for any visual-type-specific object)
    chart:legend.show: false
    chart:legend.position: Bottom
    chart:labels.show: true
    chart:categoryAxis.show: true
    chart:valueAxis.show: true

    # Data bindings — role: Table.Field
    bindings:
      Category: Sales.Region
      Y: Facts.Revenue
      # Table columns with display names and widths:
      Values:
      - field: Products.Name
        displayName: Product
        width: 250
      - field: Facts.Revenue
        displayName: Revenue
        width: 120

    # Sort
    sort: Facts.Revenue (measure) Descending

    # Filters on this visual
    filters:
    - field: Product.Category
      type: include
      values: [Bikes, Accessories]
    - field: Sales.Revenue
      type: range
      min: 1000
    - field: Product.Name
      type: advanced
      operator: contains
      value: Pro
    - field: Devices.Manufacturer
      type: topN
      count: 10
      by: Measures.TotalDevices

    # Conditional formatting
    conditionalFormatting:
      dataPoint.fill:
        mode: measure
        source: Measures.StatusColor
      values.fontColor:
        mode: gradient
        source: Facts.Revenue
        min: { color: "#FF0000", value: 0 }
        max: { color: "#00FF00", value: 100 }

    # Textbox content (type: textbox only)
    text: "Dashboard Title"
    textStyle: { fontSize: 16, bold: true, fontColor: "#1A1A1A" }

    # KPI card shorthand (type: cardVisual only)
    layout: { columns: 4, calloutSize: 28, dividers: true }
    kpis:
    - measure: Facts.Revenue
      label: Revenue
      displayUnits: 1000000
      accentColor: "#2B6CB0"

  # Page-level interactions (override default cross-filtering)
  interactions:
  - source: slicerRegion
    target: revenueChart
    type: DataFilter        # DataFilter | HighlightFilter | NoFilter

# Report-level bookmarks
bookmarks:
- name: Minimal View
  page: Sales Overview
  hide: [detailTable, footnote]
```

### Key visual types and their roles

| Type | Primary roles | Notes |
|------|--------------|-------|
| `slicer` | Values | Set height=65 with title, 44 without |
| `cardVisual` | (use `kpis:` shorthand) | Multi-tile KPI card |
| `barChart`, `clusteredBarChart` | Category, Y | Horizontal bars |
| `clusteredColumnChart` | Category, Y | Vertical columns |
| `lineChart` | Category, Y, Series | Time series |
| `donutChart`, `pieChart` | Category, Y | Part-of-whole |
| `tableEx` | Values (list of fields) | Data table with column widths |
| `pivotTable` | Rows, Columns, Values | Matrix/pivot |
| `textbox` | (use `text:` property) | Rich text display |
| `shape` | (use `style:` preset) | Background/separator |
| `lineClusteredColumnComboChart` | Category, Column, Line | Combo chart |

## Step 3: Validate and Review

```bash
pbi validate                              # structural checks
pbi render "Page" --screenshot            # HTML layout preview + PNG
```

## Design Rules

Follow these strictly to produce professional layouts.

**Page layout (1280 x 720):**
- 16px margins on all sides, 8-16px gaps between visuals
- Content width = 1248px (page width - 2 * margin)

**Slicer configuration (most common mistake):**
- Use `title` for the label, hide `slicerHeader` and `header`
- Height: 65px with title, 44px without
- Never enable both `title.show` and `slicerHeader.show` — double labels

**KPI cards:**
- Use single `cardVisual` with `kpis:` shorthand — NOT individual cards
- Height: 200-280px depending on reference labels
- Set `layout.columns` to match number of KPIs

**Charts:**
- Always set `title.text` — don't rely on auto-generated titles
- Hide legend on single-series charts: `chart:legend.show: false`
- Height: 300-450px
- Add `border` + `background` for visual separation

**Tables:**
- Always set `displayName` and `width` on every column
- Text columns: 150-300px, number columns: 80-150px

**Shapes:** Place BEFORE content visuals in YAML (lower z-order). Use bundled presets: `rounded-container`, `section-bg`, `separator`, `card-frame`.

**Naming:** Name every visual. Named visuals make exports readable, applies idempotent, and interactions/bookmarks reliable.

## Quick Imperative Commands

For one-off tweaks when YAML is overkill:

```bash
# Properties
pbi visual set "Page" visual title.text="New Title" border.radius=8
pbi page set "Page" background.color="#F5F5F5"

# Position and size
pbi visual move "Page" visual --x 16 --y 200
pbi visual resize "Page" visual --width 600 --height 400

# Bindings
pbi visual bind "Page" visual Category Sales.Region
pbi visual bind "Page" visual Y Facts.Revenue --field-type measure

# Bulk operations
pbi visual set-all border.show=true border.radius=4 --all-pages --visual-type slicer
pbi visual set-all border.color="#DDD" --all-pages --where border.color="#EDEBE9"
pbi page set-all background.color="#F5F5F5" --exclude "Hidden"

# Sort
pbi visual sort set "Page" chart Facts.Revenue --field-type measure --direction Descending

# Navigation
pbi nav page set "Page" button "Target Page"
pbi nav bookmark set "Page" button "Bookmark Name"

# Arrange/align
pbi visual arrange row "Page" s1 s2 s3 --gap 8 --margin 16
pbi visual arrange align "Page" c1 c2 --align top --distribute horizontal

# Filters
pbi filter create --page "Page" --visual chart --field Product.Category --value Bikes --value Accessories
pbi filter create --field Sales.Revenue --mode range --min 1000

# Themes
pbi theme create --primary "#002C77" --secondary "#5B9BD5"
pbi theme set dataColors='["#002C77","#5B9BD5","#ED7D31","#70AD47"]'
```

## Model Discovery

When you need to understand what data is available:

```bash
pbi model fields TableName                # columns + measures for a table
pbi model search "revenue"                # find fields by keyword
pbi model path TableA TableB              # relationship chain between tables
pbi model measure get Table.MeasureName   # see DAX expression
pbi model measure create Table MeasureName "SUM(Table[Column])"
```

## Apply Flags

| Flag | Use case |
|------|----------|
| `--dry-run` | Preview changes without writing files |
| `--page "Name"` | Only apply to one page (skip others in the YAML) |
| `--overwrite` | Full reconciliation — removes visuals NOT in the YAML |
| `--continue-on-error` | Apply what works, report what failed |

`--overwrite` is destructive (backs up the page first). Use it when redesigning a page completely. Without it, apply is additive — it only touches what's in the YAML.

## Typical Page Build Sequence

1. `pbi map` — understand the project
2. `pbi model fields` on relevant tables — know what data to bind
3. Write YAML with slicers, KPIs, charts, tables
4. `pbi apply page.yaml --dry-run` — validate
5. `pbi apply page.yaml` — create everything
6. `pbi validate` — check for issues
7. Iterate: `pbi page export "Page" -o page.yaml`, edit, `pbi apply`
