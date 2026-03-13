# PBI CLI Reference

Complete reference for the `pbi` command-line tool. All commands operate on Power BI PBIP projects using the PBIR (Enhanced Report Format).

## Project Discovery

Every command accepts `-p <path>` to specify the project. Without it, `pbi` walks up from the current directory to find a `.pbip` file.

```bash
pbi info                          # auto-detect from cwd
pbi info -p /path/to/project      # explicit path
pbi info -p ./MyReport.pbip       # point to .pbip file directly
```

## Referencing Pages and Visuals

Pages and visuals are resolved in this order:

| Method | Example | Notes |
|--------|---------|-------|
| Display name | `"Sales Overview"` | Case-insensitive |
| Partial name | `"Sales"` | Must be unambiguous |
| Folder/ID | `page1`, `a1b2c3d4e5...` | Internal hex ID |
| Index | `1`, `2`, `3` | 1-based, from list order |
| Visual type | `card`, `slicer` | Only if unique on the page |
| Friendly name | `revenueChart` | Set via `visual create --name` or `visual rename` |

## Commands

### pbi info

Tree view of the entire project — pages, visuals, positions, sizes.

```bash
pbi info
```

### pbi map

Generate a human-readable YAML index that resolves all hex IDs and shows the full hierarchy: Page → Group → Visual → Role → Field. Includes filters at all levels, sort definitions, key chart formatting, and conditional formatting. Every entry includes a relative file path.

```bash
pbi map                     # stdout
pbi map -o pbi-map.yaml     # write to file
```

Output structure:

```yaml
model:
  Product:
    columns: [Category, Sub Category, Color]
    hidden:  [Product Key]
    measures: [Product Count]
  Sales:
    columns: [Quantity, Net Price, Order Date]
    measures: [Sales Amount, Total Orders]

filters:                                              # report-level filters
  - Product.Color Categorical: Red, Blue (hidden)

pages:
  - name: Sales Overview  # active
    id: page1
    path: Report.Report/definition/pages/page1
    size: 1920 x 1080
    filters:                                          # page-level filters
      - Product.Category Categorical: Bikes
    visuals:
      - name: revenueChart
        type: clusteredColumnChart
        path: Report.Report/definition/pages/page1/visuals/a1b2c3
        position: 50, 100
        size: 600 x 400
        title: Revenue by Category
        bindings:
          Category: Product.Category
          Y: Sales.Sales Amount (measure)
        sort: Sales.Sales Amount (measure) Descending  # sort definition
        formatting: {legend: true (Top), labels: false} # key chart formatting
        conditionalFormatting:                           # conditional formatting
          - dataPoint.fill: #FF0000 @ 0 -> #FFFF00 @ 50 -> #00FF00 @ 100
        filters:                                        # visual-level filters
          - Sales.Sales Amount Advanced: >= 1000
```

---

## Page Commands

### pbi page list

```bash
pbi page list
```

Table of all pages with index, name, size, display option, visibility, and visual count.

### pbi page get

```bash
pbi page get <page>                    # all properties
pbi page get <page> <property>         # single property value
```

### pbi page set

```bash
pbi page set <page> <property> <value>
```

**Properties:**

| Property | Type | Values |
|----------|------|--------|
| `displayName` | string | Any text |
| `width` | number | Pixels |
| `height` | number | Pixels |
| `displayOption` | enum | `FitToPage`, `FitToWidth`, `ActualSize` |
| `visibility` | enum | `AlwaysVisible`, `HiddenInViewMode` |
| `background.color` | color | Page background color (`#hex`) |
| `background.transparency` | number | Background transparency (0–100) |
| `outspace.color` | color | Outspace (area outside canvas) background color |
| `outspace.transparency` | number | Outspace transparency |

```bash
pbi page set "Sales" width 1920
pbi page set "Sales" visibility HiddenInViewMode
pbi page set "Sales" background.color "#F5F5F5"
pbi page set "Sales" background.transparency 0
pbi page set "Sales" outspace.color "#E0E0E0"
```

### pbi page create

```bash
pbi page create <display-name> [--width 1280] [--height 720] [--display FitToPage]
```

### pbi page copy

Deep-copies a page including all visuals. Each visual gets a new unique ID.

```bash
pbi page copy <source-page> <new-display-name>
```

### pbi page delete

```bash
pbi page delete <page>         # interactive confirmation
pbi page delete <page> -f      # skip confirmation
```

### pbi page props

List all settable page properties with types.

---

## Visual Commands

### pbi visual list

```bash
pbi visual list <page>
```

Table of all visuals on a page with index, name, type, position, size, and z-order.

### pbi visual get

```bash
pbi visual get <page> <visual>                  # overview: formatting, bindings, sort
pbi visual get <page> <visual> <property>        # single property value
pbi visual get <page> <visual> --raw             # full JSON
```

Overview shows: position, container formatting, chart formatting, data bindings, and sort definition.

### pbi visual set

Supports single property or batch mode:

```bash
pbi visual set <page> <visual> <property> <value>          # single (legacy)
pbi visual set <page> <visual> prop=value [prop=value ...]  # batch
```

Batch examples:

```bash
pbi visual set "Sales" chart legend.show=true legend.position=Top labels.show=false
pbi visual set "Sales" chart position.x=50 position.y=100 position.width=600
pbi visual set "Sales" chart title.text="Revenue Overview" title.alignment=center background.color="#FFFFFF"
```

**Position properties** (direct values):

| Property | Type | Description |
|----------|------|-------------|
| `position.x` | number | X coordinate |
| `position.y` | number | Y coordinate |
| `position.width` | number | Width |
| `position.height` | number | Height |
| `position.z` | number | Z-order (stacking) |
| `position.tabOrder` | number | Keyboard tab sequence |
| `position.angle` | number | Rotation angle |

**Core properties:**

| Property | Type | Description |
|----------|------|-------------|
| `visualType` | string | Chart type identifier |
| `isHidden` | boolean | Hidden in view mode |

**Container formatting** (encoded as PBI visual container objects):

| Property | Type | Description |
|----------|------|-------------|
| **Background** | | |
| `background.show` | boolean | Show background |
| `background.color` | color | Background color (`#hex`) |
| `background.transparency` | number | 0–100 |
| **Border** | | |
| `border.show` | boolean | Show border |
| `border.color` | color | Border color |
| `border.width` | number | Border width |
| `border.radius` | number | Corner radius |
| **Title** | | |
| `title.show` | boolean | Show title |
| `title.text` | string | Title text |
| `title.heading` | string | Title heading level |
| `title.wrap` | boolean | Wrap title text |
| `title.color` | color | Title font color |
| `title.background` | color | Title background color |
| `title.alignment` | enum | `left`, `center`, `right` |
| `title.fontSize` | number | Title font size |
| `title.fontFamily` | string | Title font family |
| `title.bold` | boolean | Bold title |
| `title.italic` | boolean | Italic title |
| `title.underline` | boolean | Underline title |
| **Subtitle** | | |
| `subtitle.show` | boolean | Show subtitle |
| `subtitle.text` | string | Subtitle text |
| `subtitle.heading` | string | Subtitle heading level |
| `subtitle.wrap` | boolean | Wrap subtitle text |
| `subtitle.color` | color | Subtitle font color |
| `subtitle.alignment` | enum | `left`, `center`, `right` |
| `subtitle.fontSize` | number | Subtitle font size |
| `subtitle.fontFamily` | string | Subtitle font family |
| `subtitle.bold` | boolean | Bold subtitle |
| `subtitle.italic` | boolean | Italic subtitle |
| `subtitle.underline` | boolean | Underline subtitle |
| **Divider** | | |
| `divider.show` | boolean | Show divider between title and visual |
| `divider.color` | color | Divider color |
| `divider.width` | number | Divider width |
| `divider.style` | string | Divider line style |
| `divider.ignorePadding` | boolean | Divider ignores padding |
| **Spacing** | | |
| `spacing.customize` | boolean | Enable custom spacing |
| `spacing.vertical` | number | Vertical spacing |
| `spacing.belowTitle` | number | Space below title |
| `spacing.belowSubtitle` | number | Space below subtitle |
| `spacing.belowTitleArea` | number | Space below title area |
| **Padding** | | |
| `padding.top` | number | Top padding |
| `padding.bottom` | number | Bottom padding |
| `padding.left` | number | Left padding |
| `padding.right` | number | Right padding |
| **Drop Shadow** | | |
| `shadow.show` | boolean | Show drop shadow |
| `shadow.preset` | string | Shadow preset |
| `shadow.position` | string | Shadow position |
| `shadow.color` | color | Shadow color |
| `shadow.transparency` | number | Shadow transparency |
| `shadow.spread` | number | Shadow spread |
| `shadow.blur` | number | Shadow blur |
| `shadow.angle` | number | Shadow angle |
| `shadow.distance` | number | Shadow distance |
| **Visual Header** | | |
| `header.show` | boolean | Show visual header |
| `header.background` | color | Header background color |
| `header.border` | color | Header border color |
| `header.transparency` | number | Header transparency |
| `header.foreground` | color | Header icon color |
| **Tooltip** | | |
| `tooltip.show` | boolean | Show tooltip |
| `tooltip.type` | string | Tooltip type (`Default` or `ReportPage`) |
| `tooltip.section` | string | Tooltip report page name |
| `tooltip.titleColor` | color | Tooltip title font color |
| `tooltip.valueColor` | color | Tooltip value font color |
| `tooltip.fontSize` | number | Tooltip font size |
| `tooltip.fontFamily` | string | Tooltip font family |
| `tooltip.background` | color | Tooltip background color |
| `tooltip.transparency` | number | Tooltip transparency |
| **Other** | | |
| `lockAspect` | boolean | Lock aspect ratio |
| `altText` | string | Accessibility alt text |
| `stylePreset` | string | Style preset name |

**Chart formatting** (encoded as PBI visual objects — applies to charts, tables, slicers, KPIs, gauges):

*Legend (bar, column, line, area, combo, pie, donut, scatter, waterfall, ribbon, funnel, treemap):*

| Property | Type | Description |
|----------|------|-------------|
| `legend.show` | boolean | Show legend |
| `legend.position` | enum | `Top`, `Bottom`, `Left`, `Right`, `TopCenter`, `BottomCenter` |
| `legend.color` | color | Legend text color |
| `legend.fontSize` | number | Legend font size |
| `legend.fontFamily` | string | Legend font family |
| `legend.bold` | boolean | Legend bold |
| `legend.italic` | boolean | Legend italic |
| `legend.showTitle` | boolean | Show legend title |
| `legend.titleText` | string | Legend title text |

*Category axis / X-axis (bar, column, line, area, combo, waterfall, ribbon):*

| Property | Type | Description |
|----------|------|-------------|
| `xAxis.show` | boolean | Show category axis |
| `xAxis.position` | enum | `Left`, `Right` |
| `xAxis.title` | boolean | Show axis title |
| `xAxis.titleText` | string | Axis title text |
| `xAxis.titleColor` | color | Axis title color |
| `xAxis.titleFontSize` | number | Axis title font size |
| `xAxis.titleFontFamily` | string | Axis title font family |
| `xAxis.color` | color | Axis label color |
| `xAxis.fontSize` | number | Axis label font size |
| `xAxis.fontFamily` | string | Axis label font family |
| `xAxis.bold` | boolean | Axis labels bold |
| `xAxis.italic` | boolean | Axis labels italic |
| `xAxis.axisScale` | enum | `linear`, `log` |
| `xAxis.axisType` | enum | `Scalar`, `Categorical` |
| `xAxis.axisStyle` | enum | `showTitleOnly`, `showUnitOnly`, `showBoth` |
| `xAxis.start` | number | Axis range start |
| `xAxis.end` | number | Axis range end |
| `xAxis.displayUnits` | string | Display units (`0`=Auto, `1`=None, `1000`=K, `1000000`=M) |
| `xAxis.precision` | number | Decimal places |
| `xAxis.gridlines` | boolean | Show gridlines |
| `xAxis.gridlineColor` | color | Gridline color |
| `xAxis.gridlineStyle` | enum | `dashed`, `solid`, `dotted` |
| `xAxis.gridlineThickness` | number | Gridline thickness |
| `xAxis.innerPadding` | number | Inner padding between columns/bars |
| `xAxis.concatenateLabels` | boolean | Concatenate category labels |
| `xAxis.invertAxis` | boolean | Invert axis order |

*Value axis / Y-axis (bar, column, line, area, combo, scatter, waterfall, ribbon):*

| Property | Type | Description |
|----------|------|-------------|
| `yAxis.show` | boolean | Show value axis |
| `yAxis.position` | enum | `Left`, `Right` |
| `yAxis.title` | boolean | Show axis title |
| `yAxis.titleText` | string | Axis title text |
| `yAxis.titleColor` | color | Axis title color |
| `yAxis.titleFontSize` | number | Axis title font size |
| `yAxis.titleFontFamily` | string | Axis title font family |
| `yAxis.color` | color | Axis label color |
| `yAxis.fontSize` | number | Axis label font size |
| `yAxis.fontFamily` | string | Axis label font family |
| `yAxis.bold` | boolean | Axis labels bold |
| `yAxis.italic` | boolean | Axis labels italic |
| `yAxis.axisScale` | enum | `linear`, `log` |
| `yAxis.axisStyle` | enum | `showTitleOnly`, `showUnitOnly`, `showBoth` |
| `yAxis.start` | number | Axis range start |
| `yAxis.end` | number | Axis range end |
| `yAxis.displayUnits` | string | Display units (`0`=Auto, `1`=None, `1000`=K, `1000000`=M) |
| `yAxis.precision` | number | Decimal places |
| `yAxis.gridlines` | boolean | Show gridlines |
| `yAxis.gridlineColor` | color | Gridline color |
| `yAxis.gridlineStyle` | enum | `dashed`, `solid`, `dotted` |
| `yAxis.gridlineThickness` | number | Gridline thickness |
| `yAxis.invertAxis` | boolean | Invert value axis |

*Secondary Y-axis (combo charts):*

| Property | Type | Description |
|----------|------|-------------|
| `y2Axis.show` | boolean | Show secondary axis |
| `y2Axis.position` | enum | `Left`, `Right` |
| `y2Axis.title` | boolean | Show axis title |
| `y2Axis.titleText` | string | Axis title text |
| `y2Axis.titleColor` | color | Axis title color |
| `y2Axis.titleFontSize` | number | Axis title font size |
| `y2Axis.color` | color | Axis label color |
| `y2Axis.fontSize` | number | Axis label font size |
| `y2Axis.fontFamily` | string | Axis label font family |
| `y2Axis.axisScale` | enum | `linear`, `log` |
| `y2Axis.start` | number | Axis range start |
| `y2Axis.end` | number | Axis range end |
| `y2Axis.displayUnits` | string | Display units |
| `y2Axis.precision` | number | Decimal places |
| `y2Axis.gridlines` | boolean | Show gridlines |
| `y2Axis.gridlineColor` | color | Gridline color |

*Data labels (most chart types):*

| Property | Type | Description |
|----------|------|-------------|
| `labels.show` | boolean | Show data labels |
| `labels.color` | color | Label color |
| `labels.fontSize` | number | Label font size |
| `labels.fontFamily` | string | Label font family |
| `labels.bold` | boolean | Label bold |
| `labels.italic` | boolean | Label italic |
| `labels.position` | enum | `Auto`, `InsideEnd`, `OutsideEnd`, `InsideCenter`, `InsideBase` |
| `labels.format` | string | Display units (`0`=Auto, `1000`=K, `1000000`=M) |
| `labels.precision` | number | Decimal places |
| `labels.labelStyle` | enum | `Data`, `Category`, `Percent of total`, `All detail labels` (pie/donut) |
| `labels.enableBackground` | boolean | Enable label background |
| `labels.backgroundColor` | color | Label background color |
| `labels.backgroundTransparency` | number | Label background transparency |
| `labels.labelDensity` | number | Label density (how many labels to show) |

*Plot area & data colors (most chart types):*

| Property | Type | Description |
|----------|------|-------------|
| `plotArea.transparency` | number | Plot area transparency |
| `plotArea.color` | color | Plot area background |
| `dataColors.default` | color | Default data color |
| `dataColors.showAll` | boolean | Show all data colors |

*Line & area charts:*

| Property | Type | Description |
|----------|------|-------------|
| `line.show` | boolean | Show line markers |
| `line.style` | enum | `solid`, `dashed`, `dotted` |
| `line.width` | number | Line stroke width |
| `line.stepped` | boolean | Stepped line (step chart) |
| `line.shadeArea` | boolean | Shade area under line |
| `shapes.showMarkers` | boolean | Show data point markers |
| `shapes.markerShape` | string | Marker shape |
| `shapes.markerSize` | number | Marker size |

*Pie & donut:*

| Property | Type | Description |
|----------|------|-------------|
| `slices.innerRadius` | number | Donut inner radius (0 = pie, higher = larger hole) |

*Shape visual:*

| Property | Type | Description |
|----------|------|-------------|
| `shape.type` | enum | `rectangle`, `roundedRectangle`, `oval`, `triangle`, `pentagon`, `hexagon`, `octagon`, `arrow`, `star5`, `heart`, `diamond`, etc. |
| `shape.fill` | color | Fill color |
| `shape.fillShow` | boolean | Show fill |
| `shape.fillTransparency` | number | Fill transparency (0-100) |
| `shape.lineColor` | color | Line/border color |
| `shape.lineShow` | boolean | Show line/border |
| `shape.lineWeight` | number | Line weight |
| `shape.lineTransparency` | number | Line transparency (0-100) |
| `shape.roundEdge` | number | Corner rounding |
| `shape.rotation` | number | Rotation angle |

*Image visual:*

| Property | Type | Description |
|----------|------|-------------|
| `image.url` | string | Image URL |
| `image.scaling` | enum | `Fit`, `Fill`, `Normal` |

*Card visual (legacy `card`):*

| Property | Type | Description |
|----------|------|-------------|
| `categoryLabels.show` | boolean | Show category label |
| `categoryLabels.color` | color | Category label color |
| `categoryLabels.fontSize` | number | Category label font size |
| `categoryLabels.fontFamily` | string | Category label font family |
| `wordWrap.show` | boolean | Enable word wrap |

*Slicer visual:*

| Property | Type | Description |
|----------|------|-------------|
| `slicerHeader.show` | boolean | Show slicer header |
| `slicerHeader.fontColor` | color | Header font color |
| `slicerHeader.background` | color | Header background |
| `slicerHeader.fontSize` | number | Header font size |
| `slicerHeader.fontFamily` | string | Header font family |
| `slicerHeader.bold` | boolean | Header bold |
| `slicerItems.fontColor` | color | Items font color |
| `slicerItems.background` | color | Items background |
| `slicerItems.fontSize` | number | Items font size |
| `slicerItems.fontFamily` | string | Items font family |
| `slicer.selectAll` | boolean | Enable select all checkbox |
| `slicer.singleSelect` | boolean | Single selection mode |

*KPI visual:*

| Property | Type | Description |
|----------|------|-------------|
| `kpi.showIcon` | boolean | Show KPI status icon |
| `kpi.displayUnits` | string | KPI display units |
| `kpi.precision` | number | KPI decimal places |
| `kpi.direction` | enum | `Positive` (high is good), `Negative` (high is bad) |
| `kpi.goodColor` | color | Good status color |
| `kpi.neutralColor` | color | Neutral status color |
| `kpi.badColor` | color | Bad status color |
| `kpi.showTrendline` | boolean | Show trendline |
| `kpi.showGoal` | boolean | Show goal |
| `kpi.showDistance` | boolean | Show distance to goal |

*Gauge visual:*

| Property | Type | Description |
|----------|------|-------------|
| `gauge.max` | number | Gauge maximum value |
| `gauge.target` | number | Gauge target value |
| `gauge.targetColor` | color | Target line color |
| `gauge.targetShow` | boolean | Show target label |
| `gauge.calloutShow` | boolean | Show callout value |
| `gauge.calloutColor` | color | Callout value color |
| `gauge.calloutDisplayUnits` | string | Callout display units |
| `gauge.calloutPrecision` | number | Callout decimal places |

*Waterfall chart:*

| Property | Type | Description |
|----------|------|-------------|
| `waterfall.increaseColor` | color | Increase color |
| `waterfall.decreaseColor` | color | Decrease color |
| `waterfall.totalColor` | color | Total color |

*New card visual (`cardVisual`):*

| Property | Type | Description |
|----------|------|-------------|
| **Layout** | | |
| `layout.style` | string | Card layout (`Cards` or `Callout`) |
| `layout.columnCount` | long | Number of columns |
| `layout.calloutSize` | number | Callout font size |
| **Accent Bar** | | |
| `accentBar.show` | boolean | Show accent bar |
| `accentBar.color` | color | Accent bar color |
| **Card Value** | | |
| `cardValue.fontSize` | number | Value font size |
| `cardValue.fontFamily` | string | Value font family |
| `cardValue.bold` | boolean | Value bold |
| `cardValue.italic` | boolean | Value italic |
| `cardValue.color` | color | Value font color |
| `cardValue.displayUnits` | string | Display units (`0`=Auto, `1000`=K, `1000000`=M) |
| `cardValue.precision` | number | Decimal places |
| **Card Label** | | |
| `cardLabel.show` | boolean | Show label |
| `cardLabel.color` | color | Label font color |
| `cardLabel.fontSize` | number | Label font size |
| `cardLabel.fontFamily` | string | Label font family |
| `cardLabel.bold` | boolean | Label bold |
| `cardLabel.italic` | boolean | Label italic |
| **Card Shape** | | |
| `cardShape.color` | color | Card background color |
| `cardShape.radius` | number | Corner radius |
| `cardShape.transparency` | number | Background transparency |
| **Card Divider** | | |
| `cardDivider.show` | boolean | Show divider between cards |
| `cardDivider.color` | color | Divider color |
| `cardDivider.width` | number | Divider width |
| **Other** | | |
| `cardOverflow.show` | boolean | Enable text overflow |
| `cardPadding.top` | number | Internal top padding |
| `cardPadding.bottom` | number | Internal bottom padding |
| `cardPadding.left` | number | Internal left padding |
| `cardPadding.right` | number | Internal right padding |

Any property not listed above can be accessed via raw JSON dot-path (e.g. `visual.objects.legend`).

**Per-measure formatting** (`--measure` / `-m`):

Some properties (like `accentBar.color`) support per-measure selectors, allowing different formatting for each measure in a multi-measure visual. Pass `--measure` with the measure's queryRef:

```bash
# Default accent bar for all measures
pbi visual set "Sales" card accentBar.show=true accentBar.color="#4CAF50"

# Override for a specific measure
pbi visual set "Sales" card accentBar.color="#E8A83E" --measure "Sum(Devices.StaleDevices30d)"
pbi visual set "Sales" card cardValue.color="#D64554" -m "Non-Compliant"
```

**Examples:**

```bash
pbi visual set "Sales" chart background.color="#FFFFFF"
pbi visual set "Sales" chart border.show=true title.text="Revenue by Category" title.alignment=center
pbi visual set "Sales" chart legend.show=true legend.position=Top labels.show=false

# Axis formatting
pbi visual set "Sales" chart xAxis.show=true xAxis.title=true xAxis.titleText="Product Category"
pbi visual set "Sales" chart yAxis.show=true yAxis.displayUnits=1000000 yAxis.precision=1 yAxis.gridlineStyle=dashed
pbi visual set "Sales" chart yAxis.start=0 yAxis.end=1000000 yAxis.axisScale=linear

# Chart-type specific
pbi visual set "Sales" donut slices.innerRadius=50 labels.labelStyle="Percent of total"
pbi visual set "Sales" kpiCard kpi.showIcon=true kpi.direction=Positive kpi.goodColor="#00B050"
pbi visual set "Sales" gauge gauge.max=100 gauge.target=75 gauge.targetShow=true
pbi visual set "Sales" slicer slicerHeader.show=true slicerHeader.bold=true slicer.singleSelect=false
pbi visual set "Sales" waterfall waterfall.increaseColor="#00B050" waterfall.decreaseColor="#FF0000"

# New card visual
pbi visual set "Sales" card layout.style=Cards layout.columnCount=3
pbi visual set "Sales" card accentBar.show=true accentBar.color="#4CAF50"
pbi visual set "Sales" card cardValue.fontSize=24 cardValue.bold=true
pbi visual set "Sales" card cardLabel.show=true cardLabel.fontSize=10
pbi visual set "Sales" card cardShape.color="#FFFFFF" cardShape.radius=8
```

### pbi visual set-all

Apply the same property assignments to multiple visuals on a page. Use `--type` to target only visuals of a specific type.

```bash
pbi visual set-all <page> prop=value [prop=value ...]                       # all visuals on page
pbi visual set-all <page> prop=value [prop=value ...] --type slicer         # only slicers
```

```bash
# Style all slicers on a page identically
pbi visual set-all "Sales" border.radius=4 border.show=true title.fontSize=9 --type slicer

# Set background on all visuals
pbi visual set-all "Sales" background.show=true background.color="#FFFFFF"

# Style all cards
pbi visual set-all "Sales" cardValue.bold=true cardLabel.show=true --type cardVisual
```

### pbi visual paste-style

Copy formatting from one visual to another (format painter). Copies container formatting (title, border, background, shadow, padding, etc.) and chart formatting (legend, axes, labels, etc.) without affecting data bindings, filters, sort, or position.

```bash
pbi visual paste-style <page> <source> <target>                              # same page
pbi visual paste-style <page> <source> <target> --to-page "Other Page"       # cross-page
pbi visual paste-style <page> <source> <target> --container-only             # only container (title, border, bg)
pbi visual paste-style <page> <source> <target> --chart-only                 # only chart objects (legend, axes)
```

```bash
# Copy all formatting from revenueChart to profitChart on the same page
pbi visual paste-style "Sales" revenueChart profitChart

# Copy formatting to a visual on a different page
pbi visual paste-style "Sales" revenueChart chart2 --to-page "Overview"

# Copy only container formatting (title style, border, background, shadow)
pbi visual paste-style "Sales" revenueChart profitChart --container-only

# Copy only chart formatting (legend, axes, labels, data colors)
pbi visual paste-style "Sales" revenueChart profitChart --chart-only
```

### pbi visual move

```bash
pbi visual move <page> <visual> <x> <y>
```

### pbi visual resize

```bash
pbi visual resize <page> <visual> <width> <height>
```

### pbi visual create

```bash
pbi visual create <page> <visual-type> [--name NAME] [--x 0] [--y 0] [-W 300] [-H 200]
```

Use `--name` / `-n` to assign a friendly name at creation. Without it, the visual gets a hex ID.

```bash
pbi visual create "Sales" clusteredColumnChart --name revenueChart -W 600 -H 400
pbi visual create "Sales" card -n totalSales --x 700 -W 200 -H 150

# Shapes and decorative visuals
pbi visual create "Sales" shape -n headerBg -W 1920 -H 80
pbi visual create "Sales" textbox -n pageTitle --x 50 --y 10 -W 400 -H 50
pbi visual create "Sales" image -n logo --x 1700 --y 10 -W 150 -H 60
pbi visual create "Sales" actionButton -n navButton --x 1800 --y 20 -W 100 -H 40
```

Shape visuals are purely decorative (no data bindings). After creation, style them with `visual set`:

```bash
# Rectangle header background
pbi visual set "Sales" headerBg shape.type=roundedRectangle shape.fill="#003D6A" shape.lineShow=false shape.roundEdge=8

# Image
pbi visual set "Sales" logo image.url="https://example.com/logo.png" image.scaling=Fit
```

### pbi visual rename

Assign a friendly name to an existing visual.

```bash
pbi visual rename <page> <visual> <new-name>
```

```bash
pbi visual rename "Sales" 1 revenueChart
pbi visual rename "Sales" a1b2c3d4e5 totalSales
```

### pbi visual copy

```bash
pbi visual copy <page> <visual> [--to-page PAGE] [--name NAME]
```

Copy within the same page or to a different page:

```bash
pbi visual copy "Sales" revenueChart
pbi visual copy "Sales" revenueChart --to-page "Overview" --name revenueChartCopy
```

### pbi visual delete

```bash
pbi visual delete <page> <visual>         # interactive confirmation
pbi visual delete <page> <visual> -f      # skip confirmation
```

### pbi visual group

Group visuals together into a visual group container. The group's bounding box is computed automatically from the children's positions.

```bash
pbi visual group <page> <vis1> <vis2> [vis3 ...] [--name "Group Name"]
```

```bash
pbi visual group "Sales" revenueChart profitChart --name "Revenue Charts"
pbi visual group "Sales" 1 2 3 -n "Top Row"
```

### pbi visual ungroup

Dissolve a visual group, freeing its children as independent visuals.

```bash
pbi visual ungroup <page> <group>
```

```bash
pbi visual ungroup "Sales" "Revenue Charts"
```

### pbi visual sort

Set, show, or clear the sort definition on a visual. Default direction is descending.

```bash
pbi visual sort <page> <visual>                                # show current sort
pbi visual sort <page> <visual> <Table.Field>                  # sort descending (default)
pbi visual sort <page> <visual> <Table.Field> --asc            # sort ascending
pbi visual sort <page> <visual> --clear                        # remove sort definition
```

Field type (column vs measure) is auto-detected from the semantic model. Use `--measure` / `-m` to override.

```bash
pbi visual sort "Sales" chart "Sales.Sales Amount"             # sort by measure descending
pbi visual sort "Sales" chart Product.Category --asc           # sort by column ascending
pbi visual sort "Sales" chart                                  # show current sort
pbi visual sort "Sales" chart --clear                          # remove sort
```

### pbi visual format

Set, show, or clear conditional formatting on a visual. Conditional formatting makes color properties dynamic — driven by a DAX measure or a gradient color scale.

```bash
pbi visual format <page> <visual>                          # show current conditional formatting
pbi visual format <page> <visual> <object.prop> --measure <Table.Measure>     # color by measure
pbi visual format <page> <visual> <object.prop> --gradient --input <Table.Field> --min-color <hex> --min-value <n> --max-color <hex> --max-value <n>  # 2-stop gradient
pbi visual format <page> <visual> <object.prop> --clear    # remove conditional formatting
```

The `<object.prop>` references a property inside `visual.objects`, e.g. `dataPoint.fill`, `labels.color`.

**Measure-based** — the DAX measure returns a hex color string at runtime:

```bash
pbi visual format "Sales" chart dataPoint.fill --measure "Sales.ColorMeasure"
pbi visual format "Sales" chart labels.color --measure "Sales.LabelColor"
```

**Gradient (color scale)** — 2-stop or 3-stop, driven by a numeric field:

```bash
# 2-stop: red (low) to green (high)
pbi visual format "Sales" chart dataPoint.fill --gradient \
  --input "Sales.Revenue" \
  --min-color "#FF0000" --min-value 0 \
  --max-color "#00FF00" --max-value 100

# 3-stop: red -> yellow -> green
pbi visual format "Sales" chart dataPoint.fill --gradient \
  --input "Sales.Revenue" \
  --min-color "#FF0000" --min-value 0 \
  --mid-color "#FFFF00" --mid-value 50 \
  --max-color "#00FF00" --max-value 100
```

**Options:**

| Option | Description |
|--------|-------------|
| `--measure` | Measure reference (`Table.Measure`) for color-by-measure |
| `--gradient` | Enable gradient (FillRule) mode |
| `--input` | Input field for gradient (`Table.Field`) |
| `--min-color`, `--min-value` | Gradient minimum stop |
| `--mid-color`, `--mid-value` | Gradient midpoint (makes 3-stop) |
| `--max-color`, `--max-value` | Gradient maximum stop |
| `--clear` | Remove conditional formatting from the property |

**Common target properties:**

| Property | Used On |
|----------|---------|
| `dataPoint.fill` | Bar/column/pie/donut fill color |
| `labels.color` | Data label color |
| `categoryAxis.labelColor` | X-axis label color |
| `valueAxis.labelColor` | Y-axis label color |
| `legend.labelColor` | Legend text color |

### pbi visual column

List, resize, rename, or format individual columns in table (`tableEx`) and matrix (`pivotTable`) visuals.

```bash
pbi visual column <page> <visual>                                    # list all columns
pbi visual column <page> <visual> <column>                           # show column details
pbi visual column <page> <visual> <column> --width 200               # set width
pbi visual column <page> <visual> <column> --rename "Display Name"   # rename header
pbi visual column <page> <visual> <column> --align Right             # set alignment
pbi visual column <page> <visual> <column> --clear-width             # remove width override
pbi visual column <page> <visual> <column> --clear-format            # remove formatting
```

Columns can be referenced by `Table.Field`, display name, partial name, or 1-based index.

**Multiple options can be combined in a single call:**

```bash
pbi visual column "Sales" table "Sales.Revenue" --width 150 --rename "Revenue ($)" --align Right --precision 2
pbi visual column "Sales" table Product.Name --width 200 --font-color "#333333"
pbi visual column "Sales" table 1 --rename "Product" --align Left
```

**Options:**

| Option | Description |
|--------|-------------|
| `--width`, `-w` | Column width in pixels |
| `--rename` | Override column header display name |
| `--align` | Alignment: `Left`, `Center`, `Right` |
| `--font-color` | Column font color (`#hex`) |
| `--back-color` | Column background color (`#hex`) |
| `--display-units` | Label display units (0=auto, 1000=K, 1000000=M) |
| `--precision` | Decimal places |
| `--clear-width` | Remove column width override |
| `--clear-format` | Remove per-column formatting |

**Table/matrix global formatting** (via `pbi visual set`):

These properties apply to all columns/rows globally:

| Property | Type | Description |
|----------|------|-------------|
| **Column Headers** | | |
| `columnHeaders.fontColor` | color | Header font color |
| `columnHeaders.backColor` | color | Header background |
| `columnHeaders.fontSize` | number | Header font size |
| `columnHeaders.fontFamily` | string | Header font family |
| `columnHeaders.bold` | boolean | Bold headers |
| `columnHeaders.italic` | boolean | Italic headers |
| `columnHeaders.alignment` | enum | `Left`, `Center`, `Right` |
| `columnHeaders.wordWrap` | boolean | Wrap header text |
| `columnHeaders.autoSize` | boolean | Auto-size column widths |
| **Data Cells** | | |
| `values.fontColor` | color | Cell font color |
| `values.backColor` | color | Primary row background |
| `values.altBackColor` | color | Alternate row background |
| `values.fontSize` | number | Cell font size |
| `values.fontFamily` | string | Cell font family |
| `values.wordWrap` | boolean | Wrap cell text |
| `values.urlIcon` | boolean | Show URL icon |
| **Grid** | | |
| `grid.vertical` | boolean | Show vertical gridlines |
| `grid.verticalColor` | color | Vertical gridline color |
| `grid.verticalWeight` | number | Vertical gridline weight |
| `grid.horizontal` | boolean | Show horizontal gridlines |
| `grid.horizontalColor` | color | Horizontal gridline color |
| `grid.horizontalWeight` | number | Horizontal gridline weight |
| `grid.rowPadding` | number | Row padding |
| `grid.textSize` | number | Grid text size |
| **Totals Row** | | |
| `total.show` | boolean | Show totals row |
| `total.label` | string | Totals row label |
| `total.fontColor` | color | Totals font color |
| `total.backColor` | color | Totals background |
| `total.fontSize` | number | Totals font size |
| `total.fontFamily` | string | Totals font family |
| `total.bold` | boolean | Bold totals |
| **Row Headers (matrix)** | | |
| `rowHeaders.fontColor` | color | Row header font color |
| `rowHeaders.backColor` | color | Row header background |
| `rowHeaders.fontSize` | number | Row header font size |
| `rowHeaders.fontFamily` | string | Row header font family |
| `rowHeaders.bold` | boolean | Bold row headers |
| `rowHeaders.italic` | boolean | Italic row headers |
| `rowHeaders.alignment` | enum | `Left`, `Center`, `Right` |
| `rowHeaders.wordWrap` | boolean | Wrap row header text |
| `rowHeaders.steppedLayout` | boolean | Enable stepped layout |
| `rowHeaders.steppedIndent` | number | Stepped layout indent (px) |
| `rowHeaders.showExpandCollapse` | boolean | Show expand/collapse buttons |
| **Subtotals (matrix)** | | |
| `subTotals.rowSubtotals` | boolean | Show row subtotals |
| `subTotals.columnSubtotals` | boolean | Show column subtotals |
| `subTotals.rowSubtotalsPosition` | enum | `Top`, `Bottom` |
| `subTotals.perRowLevel` | boolean | Per row-level subtotals |
| `subTotals.perColumnLevel` | boolean | Per column-level subtotals |

```bash
# Global table styling via visual set
pbi visual set "Sales" table columnHeaders.backColor="#003D6A" columnHeaders.fontColor="#FFFFFF" columnHeaders.bold=true
pbi visual set "Sales" table values.backColor="#FFFFFF" values.altBackColor="#F2F2F2"
pbi visual set "Sales" table grid.vertical=true grid.horizontal=true grid.rowPadding=3
pbi visual set "Sales" table total.show=true total.label="Grand Total" total.bold=true

# Matrix-specific styling
pbi visual set "Sales" matrix rowHeaders.steppedLayout=true rowHeaders.steppedIndent=20
pbi visual set "Sales" matrix rowHeaders.showExpandCollapse=true rowHeaders.bold=true
pbi visual set "Sales" matrix subTotals.rowSubtotals=true subTotals.columnSubtotals=true
pbi visual set "Sales" matrix subTotals.rowSubtotalsPosition=Top
```

### pbi visual props

List all named visual properties with types and descriptions.

### pbi visual types

Reference for visual types and their data roles.

```bash
pbi visual types                    # all types with role names
pbi visual types scatterChart       # detailed roles for one type
```

---

## Data Binding Commands

### pbi visual bind

Bind a column (dimension) or measure (fact) to a visual's data role.

```bash
pbi visual bind <page> <visual> <role> <Table.Field> [--measure]
```

Field type (column vs measure) is auto-detected from the semantic model. Use `--measure` / `-m` to override.

```bash
pbi visual bind "Sales" chart Category Product.Category
pbi visual bind "Sales" chart Y "Sales.Sales Amount"
pbi visual bind "Sales" chart Series Product.Color
pbi visual bind "Sales" chart Tooltips "Sales.Total Orders"
```

Multi-value roles (`Y`, `Values`, `Tooltips`, etc.) accept multiple fields — call `bind` once per field.

### pbi visual unbind

```bash
pbi visual unbind <page> <visual> <role>                    # remove entire role
pbi visual unbind <page> <visual> <role> <Table.Field>      # remove specific field
```

### pbi visual bindings

```bash
pbi visual bindings <page> <visual>
```

Table of all bindings: role, table, field, and type (column/measure).

### Data Roles by Visual Type

| Visual Type | Roles |
|-------------|-------|
| Column/Bar charts | `Category` (axis), `Y` (values), `Series` (legend), `Tooltips` |
| Line/Area charts | `Category` (axis), `Y` (values), `Series` (legend), `Tooltips` |
| Combo charts | `Category`, `Y` (columns), `Y2` (lines), `Series`, `Tooltips` |
| Pie/Donut | `Category` (slices), `Y` (values), `Tooltips` |
| Scatter | `Category` (details), `X`, `Y`, `Size`, `Series`, `Tooltips` |
| Table (`tableEx`) | `Values` (multiple) |
| Matrix (`pivotTable`) | `Rows`, `Columns`, `Values` |
| Card | `Values` |
| Multi-row card | `Values` (multiple) |
| KPI | `Indicator`, `TrendAxis`, `Goal` |
| Slicer | `Values` |
| Gauge | `Y`, `MinValue`, `MaxValue`, `TargetValue`, `Tooltips` |
| Treemap | `Group`, `Values`, `Tooltips` |
| Waterfall | `Category`, `Y`, `Breakdown`, `Tooltips` |
| Ribbon | `Category`, `Y`, `Series`, `Tooltips` |
| Funnel | `Category`, `Y`, `Tooltips` |
| Map | `Category` (location), `Series`, `Size`, `Tooltips` |
| Filled map | `Category` (location), `Series`, `Tooltips` |

---

## Filter Commands

Filters operate at three levels: report (default), page (`--page`), or visual (`--page` + `--visual`). All filter commands accept `--page` and `--visual` options to target the right level.

### pbi filter list

```bash
pbi filter list                                        # report-level filters
pbi filter list --page "Sales"                         # page-level filters
pbi filter list --page "Sales" --visual chart          # visual-level filters
```

Shows field, filter type (Categorical, Advanced, TopN, RelativeDate), values/conditions, and hidden/locked status.

### pbi filter add

Four filter types:

**Categorical** — filter to specific values using `--values` / `-v`:

```bash
pbi filter add Product.Color --values "Red,Blue,Black"
pbi filter add Product.Category --values "Bikes" --page "Sales"
pbi filter add Product.Category --values "Bikes" --page "Sales" --visual chart
```

**Range** — filter to a numeric/date range using `--min` and/or `--max`:

```bash
pbi filter add "Sales.Sales Amount" --min 1000 --max 50000
pbi filter add "Sales.Sales Amount" --min 1000                 # open-ended (>= 1000)
pbi filter add Sales.OrderDate --min "2024-01-01" --page "Sales"
```

**Top N** — show only the top or bottom N items by a measure:

```bash
pbi filter add Product.Category --topn 10 --topn-by "Sales.Sales Amount"
pbi filter add Product.Category --topn 5 --topn-by "Sales.Sales Amount" --bottom
pbi filter add Product.Category --topn 10 --topn-by "Sales.Total Orders" --page "Sales"
```

**Relative Date** — filter a date field relative to the current date:

```bash
pbi filter add Calendar.Date --relative "InLast 7 Days"
pbi filter add Calendar.Date --relative "InThis 1 Months"
pbi filter add Calendar.Date --relative "InNext 2 Weeks" --no-include-today
pbi filter add Calendar.Date --relative "InLast 1 Years" --page "Sales"
```

Relative date format: `<Operator> <Count> <Unit>` where:
- Operators: `InLast`, `InThis`, `InNext`
- Units: `Days`, `Weeks`, `Months`, `Quarters`, `Years`

**Options:**

| Option | Description |
|--------|-------------|
| `--values`, `-v` | Comma-separated values for categorical filter |
| `--min` | Minimum value for range filter |
| `--max` | Maximum value for range filter |
| `--topn` | Number of items for Top N filter |
| `--topn-by` | Order-by field for Top N (`Table.Measure`) |
| `--bottom` | Use Bottom N instead of Top N |
| `--relative` | Relative date expression (`"InLast 7 Days"`) |
| `--include-today/--no-include-today` | Include today in relative date (default: yes) |
| `--hidden` | Hide filter from view mode (users can't see it) |
| `--locked` | Lock filter in view mode (users can see but can't change it) |
| `--measure`, `-m` | Treat field as a measure instead of column |
| `--page` | Target page level (omit for report level) |
| `--visual` | Target visual level (requires `--page`) |

Field type is auto-detected from the semantic model. Use `--measure` / `-m` to override.

```bash
pbi filter add Product.Color --values "Red,Blue" --hidden --locked
pbi filter add "Sales.Sales Amount" --min 1000 --hidden --page "Sales" --visual chart
pbi filter add Product.Category --topn 5 --topn-by "Sales.Sales Amount" --hidden
pbi filter add Calendar.Date --relative "InLast 30 Days" --hidden --page "Sales"
```

### pbi filter remove

Remove by field reference (`Table.Field`) or internal filter name:

```bash
pbi filter remove Product.Color                        # remove by field reference
pbi filter remove Filter_4c73676c90f2d32d              # remove by filter name
pbi filter remove Product.Color --page "Sales"         # from page level
pbi filter remove Product.Color --page "Sales" --visual chart  # from visual level
```

---

## Semantic Model Commands

### pbi model tables

```bash
pbi model tables
```

List all tables with column and measure counts.

### pbi model columns

```bash
pbi model columns <table>              # visible columns only
pbi model columns <table> --hidden     # include hidden key columns
```

### pbi model measures

```bash
pbi model measures <table>
```

Lists measures with their DAX expressions and format strings.

### pbi model fields

```bash
pbi model fields <table>
```

Lists all columns and measures with their `Table.Field` reference — the exact format used by `visual bind`.

---

## Theme Commands

### pbi theme list

Show active base and custom themes.

```bash
pbi theme list
```

### pbi theme apply

Apply a custom theme JSON file to the project. Copies the theme to `StaticResources/RegisteredResources/` and updates `report.json`.

```bash
pbi theme apply <theme.json>
```

```bash
pbi theme apply ./corporate-theme.json
pbi theme apply /path/to/dark-mode.json
```

### pbi theme export

Export the active custom theme to a standalone JSON file.

```bash
pbi theme export <output-path>
```

```bash
pbi theme export ./my-theme-backup.json
```

### pbi theme remove

Remove the custom theme from the project (reverts to base theme only).

```bash
pbi theme remove
```

**Theme JSON structure:**

```json
{
  "name": "Corporate Theme",
  "dataColors": ["#0078D4", "#40E0D0", "#FFA500", "#DC143C"],
  "background": "#FFFFFF",
  "foreground": "#323130",
  "tableAccent": "#0078D4",
  "textClasses": {
    "label": { "fontFace": "Segoe UI", "fontSize": 11 },
    "title": { "fontFace": "Segoe UI Semibold", "fontSize": 14 }
  }
}
```

---

## PBIR File Structure

```
Project/
├── Project.pbip                                # entry point
├── Project.Report/
│   ├── definition.pbir                         # report → model reference
│   └── definition/
│       ├── report.json                         # report-level settings, themes
│       └── pages/
│           ├── pages.json                      # page order, active page
│           └── <page-id>/
│               ├── page.json                   # page properties
│               └── visuals/
│                   └── <visual-id>/
│                       └── visual.json         # visual container + config
└── Project.SemanticModel/
    └── definition/
        └── tables/
            └── <Table>.tmdl                    # columns, measures, partitions
```

**visual.json structure:**

```
{
  name           — visual identifier (hex ID or friendly name)
  position       — {x, y, width, height, z, tabOrder, angle}
  visual         — {
    visualType          — chart type string
    query.queryState    — data bindings by role
    query.sortDefinition — sort field and direction
    objects             — chart formatting (legend, axes, labels, dataPoint, ...)
                          Each key maps to an array of entries. Static formatting
                          is at index 0. Conditional formatting adds entries with
                          a "selector" (dataViewWildcard) and expression-based
                          values (Measure or FillRule instead of Literal).
    visualContainerObjects — container formatting (background, border, title, ...)
  }
  filterConfig   — visual-level filters
  isHidden       — visibility flag
  parentGroupName — group membership (if grouped)
}
```

**Static vs Conditional formatting:**

- `pbi visual set` writes **static** values (Literal expressions) to `visual.objects` and `visual.visualContainerObjects`. These are fixed colors, sizes, and flags.
- `pbi visual format` writes **conditional** values (Measure or FillRule expressions) to `visual.objects` as separate entries with a selector. These are dynamic — evaluated at runtime against the data.
- Both can coexist on the same visual. Static formatting provides the baseline; conditional formatting overrides specific properties when data-driven rules apply.
