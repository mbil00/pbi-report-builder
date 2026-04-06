# PBI CLI — Visual Design Guidelines

Practical rules for producing clean, professional Power BI layouts. Each section shows the canonical YAML pattern, explains the pitfalls, and gives exact dimensions.

Read this before styling any report.

---

## Page Layout

**Standard canvas:** 1280 x 720 (default) or 1920 x 1080 for dense dashboards.

**Margins and spacing:**

| Concept | Value | Notes |
|---------|-------|-------|
| Page margin | 16 px | Consistent on all sides |
| Gap between visuals | 8–16 px | Use `pbi calc row` or `pbi calc grid` |
| Slicer row height | 65 px | Title + dropdown, no padding waste |
| KPI strip height | 200–280 px | Depends on reference labels |
| Chart height | 300–450 px | Shorter charts = wider feeling |
| Table height | Fill remaining | Use the rest of the page |

**Typical vertical stacking (1280 x 720):**

```
y=8     Slicer row         (65 px tall)
y=90    KPI strip           (200 px)
y=306   Charts / content    (remaining)
```

Use `pbi calc row N --width 1248 --margin 16 --gap 8` to compute horizontal positions. The content width is page width minus twice the margin.

---

## Slicers

Slicers are the most commonly misconfigured visual. Follow these rules strictly.

### The three "headers" — understand what each one is

A slicer has three independent label layers. Agents routinely enable all of them, creating triple-stacked labels with the dropdown pushed off-screen.

| Property | What it controls | Default |
|----------|-----------------|---------|
| `title.show` | Visual container title bar (shared by all visual types) | false |
| `slicerHeader.show` | Slicer's own built-in field label (shows the bound field name) | true |
| `header.show` | Visual control bar — focus mode, drill, more options icons | true |

**Rule: Pick ONE label source. Hide the others.**

### Recommended slicer pattern

Use the visual `title` for the label (you control the text). Hide the slicer's own header (it just duplicates the field name). Hide the control bar header (unnecessary on slicers).

```yaml
- name: slicerRegion
  type: slicer
  position: 16, 8
  size: 300 x 65
  title:
    show: true
    text: Region
    fontSize: 10
  slicerHeader:
    show: false
  header:
    show: false
  bindings:
    Values: Sales.Region
```

**Height: 65 px.** This fits the title (~22 px) and dropdown (~32 px) with minimal padding. Going shorter clips the dropdown. Going taller adds empty white space.

**If you hide the title too** (label-less slicer), reduce height to 44 px:

```yaml
- name: slicerRegion
  type: slicer
  position: 16, 8
  size: 300 x 44
  title:
    show: false
  slicerHeader:
    show: false
  header:
    show: false
  bindings:
    Values: Sales.Region
```

### Slicer row pattern

A horizontal row of slicers across the top of the page. Use `pbi calc row` to compute evenly spaced positions.

```bash
# 4 slicers across a 1280-wide page with 16px margins and 8px gaps
pbi calc row 4 --width 1248 --margin 16 --gap 8 --height 65
```

```yaml
visuals:
- name: slicerRegion
  type: slicer
  position: 16, 8
  size: 303 x 65
  title: { show: true, text: Region, fontSize: 10 }
  slicerHeader: { show: false }
  header: { show: false }
  bindings: { Values: Sales.Region }

- name: slicerCategory
  type: slicer
  position: 327, 8
  size: 303 x 65
  title: { show: true, text: Category, fontSize: 10 }
  slicerHeader: { show: false }
  header: { show: false }
  bindings: { Values: Products.Category }

- name: slicerYear
  type: slicer
  position: 638, 8
  size: 303 x 65
  title: { show: true, text: Year, fontSize: 10 }
  slicerHeader: { show: false }
  header: { show: false }
  bindings: { Values: Calendar.Year }

- name: slicerStatus
  type: slicer
  position: 949, 8
  size: 303 x 65
  title: { show: true, text: Status, fontSize: 10 }
  slicerHeader: { show: false }
  header: { show: false }
  bindings: { Values: Orders.Status }
```

### What goes wrong without these rules

| Mistake | Result |
|---------|--------|
| `title.show: true` + `slicerHeader.show: true` | Two labels stacked. "Region" appears twice. |
| Height < 60 px with title enabled | Dropdown input gets clipped or hidden entirely |
| `header.show: true` (default) | Control bar icons eat 20 px of vertical space |
| All three enabled | ~60 px consumed by labels, dropdown pushed below visible area |

---

## KPI Cards (cardVisual)

Use the `kpis:` shorthand — it's significantly easier than manual bindings and produces correct PBIR.

### Horizontal KPI strip

```yaml
- name: kpiStrip
  type: cardVisual
  position: 16, 90
  size: 1248 x 200

  layout:
    columns: 4           # tiles per row
    calloutSize: 28       # main number font size
    dividers: true        # lines between tiles
    cellPadding: 8

  accentBar:
    show: true
    position: Top         # Top or Left
    width: 4

  kpis:
  - measure: Facts.Revenue
    label: Revenue
    displayUnits: 1000000
    accentColor: '#2B6CB0'

  - measure: Facts.Orders
    label: Orders
    accentColor: '#2B7A4B'

  - measure: Facts.AvgValue
    label: Avg. Value
    accentColor: '#9B2C2C'

  - measure: Facts.Customers
    label: Customers
    accentColor: '#6B46C1'
```

**Sizing:** 200 px height for simple KPIs. 250–280 px if using `referenceLabels`.

**Do not** create individual `card` visuals for each KPI — use a single `cardVisual` with the `kpis:` shorthand and `layout.columns` set to the number of tiles.

---

## Charts

### Common chart pattern

```yaml
- name: revenueByRegion
  type: barChart                           # or clusteredColumnChart, lineChart, etc.
  position: 16, 306
  size: 600 x 380
  title: { show: true, text: Revenue by Region }
  border: { show: true, color: '#E2E2E2', radius: 8 }
  background: { color: '#FFFFFF' }
  chart:legend.show: false                 # hide legend for single-series charts
  chart:labels.show: true                  # show data labels
  bindings:
    Category: Regions.RegionName
    Y: Facts.Revenue
  sort: Facts.Revenue (measure) Descending
```

**Rules:**
- Always set a `title.text` — don't rely on auto-generated titles
- Add `border` + `background` on light-background pages for visual separation
- Hide the legend on single-series charts (`chart:legend.show: false`)
- For multi-series, position legend at bottom or right (`chart:legend.position: Bottom`)
- 300–450 px height works for most charts
- Reference measures with `(measure)` suffix in sort to disambiguate from columns

### Donut charts

```yaml
- name: categoryBreakdown
  type: donutChart
  position: 640, 306
  size: 600 x 380
  title: { show: true, text: Category Breakdown }
  border: { show: true, color: '#E2E2E2', radius: 8 }
  background: { color: '#FFFFFF' }
  chart:legend.show: true
  chart:legend.position: Right
  chart:labels.show: true
  bindings:
    Category: Products.Category
    Y: Facts.Revenue
```

---

## Tables

### Standard data table

```yaml
- name: orderDetail
  type: tableEx
  position: 16, 700
  size: 1248 x 400
  title: { show: true, text: Order Details }
  border: { show: true, color: '#E2E2E2', radius: 8 }
  background: { color: '#FFFFFF' }
  bindings:
    Values:
    - field: Products.ProductName
      displayName: Product
      width: 250
    - field: Regions.RegionName
      displayName: Region
      width: 150
    - field: Facts.Revenue
      displayName: Revenue
      width: 120
    - field: Facts.Orders
      displayName: Orders
      width: 100
```

**Rules:**
- Always set `displayName` — raw field names (`ProductName`) are not user-friendly
- Always set `width` — default widths are usually too wide or too narrow
- Text columns: 150–300 px. Number columns: 80–150 px
- Add conditional formatting for key metrics (gradient or rules-based)
- Tables expand to fill their height with scrolling — make them tall enough to show ~10–15 rows without scrolling

---

## Shapes (containers and separators)

Shapes are invisible structural elements — backgrounds, section dividers, and grouping containers. Use the bundled presets.

### Section background

```yaml
- name: sectionBg
  type: shape
  position: 16, 300
  size: 1248 x 400
  style: section-bg            # bundled preset: subtle fill + rounded border
```

### Card container

```yaml
- name: cardBg
  type: shape
  position: 16, 90
  size: 300 x 200
  style: rounded-container     # bundled preset: filled rounded rect with shadow
```

### Horizontal separator

```yaml
- name: divider
  type: shape
  position: 16, 290
  size: 1248 x 1
  style: separator             # bundled preset: thin line
```

**Rule:** Shapes go BEHIND content visuals. Place them before the content visuals in the YAML so they render at a lower z-order. Use `pbi visual group` to group a shape with its content visuals for easier management.

---

## Textboxes

Use textboxes for page headers and section titles. Supported via the `text:` and `textStyle:` properties.

```yaml
- name: pageTitle
  type: textbox
  position: 16, 8
  size: 400 x 32
  text: "Fleet Intelligence Dashboard"
  textStyle:
    fontSize: 16
    fontColor: '#1A1A1A'
    bold: true
    fontFamily: Segoe UI Semibold
  background: { show: false }
  border: { show: false }
```

**Sizing:** Height = fontSize + 16 px padding. A 16pt title needs ~32 px height.

---

## Interactions

By default, every visual cross-filters every other visual. This is usually wrong for slicers — you want slicers to filter charts and tables, but not other slicers.

```yaml
interactions:
- source: slicerRegion
  target: slicerCategory
  type: NoFilter              # slicers don't filter each other
- source: slicerRegion
  target: revenueChart
  type: DataFilter            # slicer filters chart (default, but be explicit)
```

**Types:** `DataFilter` (default cross-filter), `HighlightFilter` (highlight only), `NoFilter` (no effect).

---

## Style Consistency

For a polished look, define styles once and reference them everywhere:

```bash
# Create once
pbi catalog create style border.show=true border.color="#E2E2E2" \
  border.radius=8 background.color="#FFFFFF" --name card-panel
```

```yaml
# Reference everywhere
- name: chart1
  type: barChart
  style: card-panel
  ...

- name: chart2
  type: donutChart
  style: card-panel
  ...

- name: table1
  type: tableEx
  style: card-panel
  ...
```

Use `pbi catalog apply style/card-panel "Dashboard" --visual-type cardVisual` or YAML `style: card-panel` to reuse it.
