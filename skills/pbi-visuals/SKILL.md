---
name: pbi-visuals
description: "Power BI report visual design and styling with the `pbi` CLI — use when building page layouts, creating/styling visuals, writing apply YAML, configuring charts/slicers/KPIs/tables, setting up filters, conditional formatting, interactions, bookmarks, themes, catalog assets (styles, visual templates, components, page templates), or visual auditing. Triggers on: dashboard layout, report page, visual properties, slicer configuration, KPI card, chart formatting, data binding, cross-filtering, YAML apply, page export, visual styling, theme colors, conditional formatting, report design, catalog apply, visual template, component stamp."
---

# Power BI Visual Design & Styling

You are designing Power BI report pages using the `pbi` CLI. This skill covers the YAML-first declarative workflow for building, styling, and laying out professional report pages.

## Workflow: Always Start with YAML

The declarative YAML approach is faster, produces fewer errors, and handles multiple changes atomically.

```bash
# New page: write YAML from scratch
# Existing page: export first, then edit
pbi page export "Sales" -o sales.yaml

# Preview changes
pbi diff sales.yaml

# Validate without writing
pbi apply sales.yaml --dry-run

# Apply
pbi apply sales.yaml

# Verify
pbi validate
```

**Apply flags:**

| Flag | Use case |
|------|----------|
| `--dry-run` | Preview changes without writing files |
| `--page "Name"` | Only apply one page from multi-page YAML |
| `--overwrite` | Full reconciliation — removes visuals NOT in YAML |
| `--continue-on-error` | Apply what works, report what failed |

YAML also accepts stdin: `cat page.yaml | pbi apply -`

## Discovery (Before You Build)

```bash
pbi map                                   # full project overview
pbi page list                             # pages with sizes and visual counts
pbi visual list "PageName"               # visuals with types and positions
pbi visual get "Page" visual --full       # everything: props, objects, columns, filters, sort
pbi visual tree "Page"                    # group hierarchy
pbi model fields TableName                # available columns + measures for binding
pbi visual types                          # all visual types
pbi visual types clusteredBarChart        # roles for one type
pbi visual properties --visual-type cardVisual  # all schema-derived properties
```

## YAML Spec Reference

### Page structure

```yaml
pages:
- name: Sales Overview          # display name (required)
  width: 1280                   # default 1280
  height: 720                   # default 720

  visuals:
  - name: slicerRegion          # name every visual (critical for idempotency)
    type: slicer                # visual type
    position: 16, 8             # x, y
    size: 300 x 65              # width x height
    style: card-panel           # apply a saved style preset

    # Container properties (work on all visual types)
    title: { show: true, text: Region, fontSize: 10 }
    background: { show: true, color: "#FFFFFF", transparency: 0 }
    border: { show: true, color: "#E2E2E2", radius: 8 }
    shadow: { show: true }

    # Chart-specific properties (auto-resolved from PBI schema)
    chart:legend.show: false
    chart:legend.position: Bottom
    chart:labels.show: true
    chart:categoryAxis.show: true
    chart:valueAxis.show: true

    # Data bindings — role: Table.Field
    bindings:
      Category: Sales.Region
      Y: Facts.Revenue

    # Sort
    sort: Facts.Revenue (measure) Descending

    # Filters on this visual
    filters:
    - field: Product.Category
      type: include
      values: [Bikes, Accessories]

    # Conditional formatting
    conditionalFormatting:
      dataPoint.fill:
        mode: measure
        source: Measures.StatusColor
```

### Visual types and their data roles

| Type | Primary roles | Notes |
|------|--------------|-------|
| `slicer` | Values | Height 65px with title, 44px without |
| `cardVisual` | (use `kpis:` shorthand) | Multi-tile KPI card |
| `barChart` | Category, Y | Horizontal bars |
| `clusteredColumnChart` | Category, Y | Vertical columns |
| `lineChart` | Category, Y, Series | Time series |
| `donutChart`, `pieChart` | Category, Y | Part-of-whole |
| `tableEx` | Values (list) | Data table with column widths |
| `pivotTable` | Rows, Columns, Values | Matrix/pivot |
| `textbox` | (use `text:` property) | Rich text display |
| `shape` | (use `style:` preset) | Background/separator |
| `lineClusteredColumnComboChart` | Category, Column, Line | Combo chart |
| `map` | Location, Size | Bubble map |
| `filledMap` | Location, Color saturation | Choropleth |
| `treemap` | Group, Values | Treemap |
| `waterfallChart` | Category, Y | Waterfall |
| `funnel` | Category, Y | Funnel |
| `kpi` | Indicator, Trend axis, Target goals | KPI indicator |
| `gauge` | Value, Min, Max, Target | Gauge |
| `scatterChart` | X, Y, Size, Legend | Scatter |

## Design Rules

Follow these strictly to produce professional layouts.

### Page layout (1280 x 720)

- 16px margins on all sides, 8-16px gaps between visuals
- Content width = 1248px (page width - 2 x margin)
- Use `pbi calc row N --width 1248 --margin 16 --gap 8` to compute positions

**Typical vertical stacking:**
```
y=8     Slicer row          (65px)
y=90    KPI strip           (200px)
y=306   Charts / content    (remaining)
```

### Slicers — the most common mistake

A slicer has three independent label layers. Enabling all of them creates triple-stacked labels with the dropdown pushed off-screen.

| Property | What it is | Recommended |
|----------|-----------|-------------|
| `title` | Container title bar | **show: true** — your label |
| `slicerHeader` | Built-in field label | **show: false** — duplicates field name |
| `header` | Control bar icons | **show: false** — unnecessary |

**Rule: Pick ONE label source. Hide the others.**

```yaml
- name: slicerRegion
  type: slicer
  position: 16, 8
  size: 300 x 65              # 65px with title, 44px without
  title: { show: true, text: Region, fontSize: 10 }
  slicerHeader: { show: false }
  header: { show: false }
  bindings: { Values: Sales.Region }
```

### KPI cards

Use a single `cardVisual` with `kpis:` shorthand — NOT individual cards.

```yaml
- name: kpiStrip
  type: cardVisual
  position: 16, 90
  size: 1248 x 200
  layout: { columns: 4, calloutSize: 28, dividers: true }
  kpis:
  - measure: Facts.Revenue
    label: Revenue
    displayUnits: 1000000
    accentColor: "#2B6CB0"
  - measure: Facts.Orders
    label: Orders
    accentColor: "#2B7A4B"
```

### Charts

```yaml
- name: revenueByRegion
  type: barChart
  position: 16, 306
  size: 600 x 380
  title: { show: true, text: Revenue by Region }
  border: { show: true, color: "#E2E2E2", radius: 8 }
  background: { color: "#FFFFFF" }
  chart:legend.show: false         # hide on single-series
  chart:labels.show: true
  bindings:
    Category: Regions.RegionName
    Y: Facts.Revenue
  sort: Facts.Revenue (measure) Descending
```

- Always set `title.text` — don't rely on auto-generated titles
- Hide legend on single-series charts
- Height: 300-450px
- Add `border` + `background` for visual separation

### Tables

```yaml
- name: orderDetail
  type: tableEx
  position: 16, 700
  size: 1248 x 400
  title: { show: true, text: Order Details }
  bindings:
    Values:
    - field: Products.Name
      displayName: Product
      width: 250
    - field: Facts.Revenue
      displayName: Revenue
      width: 120
```

- Always set `displayName` and `width` on every column
- Text columns: 150-300px, number columns: 80-150px

### Shapes (backgrounds and separators)

Place shapes BEFORE content visuals in YAML (lower z-order). Use bundled presets:

| Preset | Description |
|--------|-------------|
| `rounded-container` | Filled rounded rect with shadow |
| `section-bg` | Subtle fill for page section zoning |
| `separator` | Thin horizontal/vertical line |
| `card-frame` | Transparent with border only |

```yaml
- name: sectionBg
  type: shape
  position: 16, 300
  size: 1248 x 400
  style: section-bg
```

### Textboxes

```yaml
- name: pageTitle
  type: textbox
  position: 16, 8
  size: 400 x 32
  text: "Dashboard Title"
  textStyle: { fontSize: 16, bold: true, fontColor: "#1A1A1A" }
  background: { show: false }
  border: { show: false }
```

Height = fontSize + 16px padding.

## Filters in YAML

```yaml
filters:
- field: Product.Category
  type: include
  values: [Bikes, Accessories]
- field: Sales.Revenue
  type: range
  min: 1000
  max: 50000
- field: Product.Name
  type: advanced
  operator: contains
  value: Pro
- field: Devices.Manufacturer
  type: topN
  count: 10
  by: Measures.TotalDevices
  direction: Top
```

Advanced operators: `contains`, `starts-with`, `is`, `is-not`, `greater-than`, `less-than`, `is-blank`, `is-not-blank`, `is-empty`, `is-not-empty`. Compound filters: add `operator2:`, `value2:`, `logic: and|or`.

## Conditional Formatting in YAML

```yaml
conditionalFormatting:
  # Measure-driven (DAX returns the color)
  dataPoint.fill:
    mode: measure
    source: Measures.StatusColor

  # Gradient
  values.fontColor:
    mode: gradient
    source: Sales.Revenue
    min: { color: "#FF0000", value: 0 }
    max: { color: "#00FF00", value: 100 }

  # Rules-based
  values.backColor:
    mode: rules
    source: Devices.ComplianceState
    rules:
    - if: Compliant
      color: "#E6F4EA"
    - if: NonCompliant
      color: "#FFEBEE"
    else: "#FFFFFF"
```

## Interactions in YAML

```yaml
interactions:
- source: slicerRegion
  target: slicerCategory
  type: NoFilter            # slicers don't filter each other
- source: slicerRegion
  target: revenueChart
  type: DataFilter          # explicit (default behavior)
```

Types: `DataFilter`, `HighlightFilter`, `NoFilter`.

## Bookmarks in YAML

```yaml
bookmarks:
- name: Minimal View
  page: Sales Overview
  hide: [detailTable, footnote]
```

## Catalog — Styles, Components, Visual Templates, Page Templates

All reusable assets are managed through the unified `pbi catalog` command. Four kinds: **visual**, **style**, **component**, **page**. Three scopes: **project**, **global**, **bundled** (read-only built-ins).

### Styles

```bash
# Create a style from properties
pbi catalog create style --name card-panel border.show=true border.color="#E2E2E2" border.radius=8

# Capture style from an existing visual
pbi catalog create style --from-visual "Overview" --visual myCard --name card-panel

# Apply to visuals
pbi catalog apply style/card-panel "Page" --visual chart              # one visual
pbi catalog apply style/card-panel "Page" --visual-type barChart      # all of a type

# In YAML — same as before
- name: chart1
  type: barChart
  style: card-panel           # single style
  style: [base, dark-theme]   # multiple, applied in order
```

### Visual Templates

Parameterized single-visual templates with `{{ param }}` placeholders.

```bash
# Browse bundled templates
pbi catalog list --kind visual
pbi catalog get visual/bar-chart

# Create from report
pbi catalog create visual --from-visual "Page" --visual chart --name my-chart

# Apply with parameter overrides
pbi catalog apply visual/bar-chart "Page" --x 16 --y 200 \
  --set category=Products.Name --set value=Sales.Revenue
```

### Components

Multi-visual groups with coordinated layout and parameterization.

```bash
# Save a visual group as a component
pbi catalog create component --from-visual "Dashboard" --visual "KPI Group" --name kpi-strip

# Stamp onto a page
pbi catalog apply component/kpi-strip "Page" --x 16 --y 90

# Batch stamp a row with per-instance values
pbi catalog apply component/kpi-strip "Page" --row 4 --gap 12 \
  --set-each title=Revenue,Margin,Pipeline,Backlog
```

### Page Templates

```bash
# Save a page layout
pbi catalog create page --from-visual "Overview" --name dashboard-layout --scope global

# Apply to a page
pbi catalog apply page/dashboard-layout "New Page"
pbi catalog apply page/dashboard-layout "New Page" --overwrite   # remove non-template visuals

# Or use shorthand on page create
pbi page create "Intro" --from-template corp-intro --template-global
```

### Catalog Management

```bash
pbi catalog list --kind style --scope bundled       # browse bundled styles
pbi catalog clone visual/bar-chart --to-global      # share across projects
pbi catalog register my-chart.yaml --kind visual    # import from file
pbi catalog validate                                # verify all catalog YAML
pbi catalog delete style/old --force
```

## Themes

```bash
pbi theme create "Brand" --accent=#0078D4 --data-colors=#0078D4,#E94560,#1AAB40
pbi theme get                             # palette overview
pbi theme set foreground=#111111          # modify with color cascade
pbi theme set dataColors=#0078D4,#E94560  # data color palette
pbi theme properties                      # all writable properties
pbi theme audit                           # audit theme changes vs defaults

# Visual style overrides (defaults per visual type)
pbi theme style set columnChart legend.show=true legend.position=RightCenter
pbi theme style set * background.show=true background.transparency=0    # all types

# Theme-level conditional formatting
pbi theme format get
pbi theme format set dataPoint.fill --mode measure --source Measures.StatusColor
pbi theme format clear dataPoint.fill

# Theme presets
pbi theme save "corporate" --global
pbi theme load "corporate"
pbi theme preset list
pbi theme preset clone "corporate" --to-project
```

## Page Sections

Create section backgrounds (shape + title, grouped) in one command:

```bash
pbi page section create "Dashboard" "Key Metrics" \
  --x 16 --y 130 --width 1248 --height 220 \
  --background "#F5F5F5" --radius 10 \
  --title-color "#002C77" --title-size 14
```

## Imperative Commands (Quick Tweaks)

When YAML is overkill for a one-off change:

```bash
pbi visual set "Page" chart title.text="New Title" border.radius=8
pbi visual move "Page" chart --x 16 --y 200
pbi visual resize "Page" chart --width 600 --height 400
pbi visual bind "Page" chart Category Sales.Region
pbi visual arrange row "Page" s1 s2 s3 --gap 8 --margin 16
pbi visual arrange column "Page" v1 v2 v3 --gap 8
pbi visual arrange grid "Page" v1 v2 v3 v4 --columns 2 --gap 8
pbi visual arrange align "Page" c1 c2 --align top --distribute horizontal
pbi visual sort set "Page" chart Facts.Revenue --direction desc
pbi visual column "Page" table "Revenue" --width 120 --rename "Rev ($)"
pbi visual paste-style "Page" source-chart target-chart  # copy formatting
pbi nav page set "Page" button "Target Page"
```

### Visual Inspection & Audit

```bash
pbi visual audit "Page"                   # audit visual state and properties
pbi visual objects "Page" chart            # list data-binding objects
pbi visual diff "Page" chart spec.yaml    # diff a visual against YAML
pbi visual page-diff "Page"               # show page visual differences
pbi visual inspect "Page" chart            # inspect visual capabilities
pbi visual tree "Page"                     # show group hierarchy
```

## Bulk Operations

```bash
pbi visual set-all border.show=true border.radius=4 --all-pages --visual-type slicer
pbi visual set-all border.color="#DDD" --all-pages --where border.color="#EDEBE9"
pbi page set-all background.color="#F5F5F5" --exclude "Hidden"
```

## Validation and Preview

```bash
pbi validate                              # structural + schema checks
pbi validate --strict                     # also fail on warnings
pbi render "Page" -o page.html            # HTML layout mockup
pbi render "Page" --screenshot            # HTML + PNG
```

## Typical Page Build Sequence

1. `pbi map` — understand the project
2. `pbi model fields TableName` — know what data to bind
3. Write YAML with slicers, KPIs, charts, tables
4. `pbi apply page.yaml --dry-run` — validate
5. `pbi apply page.yaml` — create everything
6. `pbi validate` — check for issues
7. Iterate: `pbi page export "Page" -o page.yaml`, edit, `pbi apply`

## Naming Strategy

Name every visual (`name:` in YAML, `--name` on create). Named visuals make:
- Exports readable
- Applies idempotent (same YAML = same result)
- Interactions and bookmarks reliable (reference by name)
