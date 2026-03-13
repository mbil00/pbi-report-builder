# Visual Commands

## pbi visual list

```bash
pbi visual list <page>
```

Table of all visuals on a page with index, name, type, position, size, and z-order.

## pbi visual get

```bash
pbi visual get <page> <visual>                  # overview: formatting, bindings, sort
pbi visual get <page> <visual> <property>        # single property value
pbi visual get <page> <visual> --raw             # full JSON
```

Overview shows: position, container formatting, chart formatting, data bindings, and sort definition.

## pbi visual set

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

**Per-measure formatting** (`--measure` / `-m`):

Some properties (like `accentBar.color`) support per-measure selectors, allowing different formatting for each measure in a multi-measure visual. Pass `--measure` with the measure's queryRef:

```bash
# Default accent bar for all measures
pbi visual set "Sales" card accentBar.show=true accentBar.color="#4CAF50"

# Override for a specific measure
pbi visual set "Sales" card accentBar.color="#E8A83E" --measure "Sum(Devices.StaleDevices30d)"
pbi visual set "Sales" card cardValue.color="#D64554" -m "Non-Compliant"
```

See [Properties Reference](properties.md) for all available properties.

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

## pbi visual set-all

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

## pbi visual paste-style

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

## pbi visual move

```bash
pbi visual move <page> <visual> <x> <y>
```

## pbi visual resize

```bash
pbi visual resize <page> <visual> <width> <height>
```

## pbi visual create

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

## pbi visual rename

Assign a friendly name to an existing visual.

```bash
pbi visual rename <page> <visual> <new-name>
```

```bash
pbi visual rename "Sales" 1 revenueChart
pbi visual rename "Sales" a1b2c3d4e5 totalSales
```

## pbi visual copy

```bash
pbi visual copy <page> <visual> [--to-page PAGE] [--name NAME]
```

Copy within the same page or to a different page:

```bash
pbi visual copy "Sales" revenueChart
pbi visual copy "Sales" revenueChart --to-page "Overview" --name revenueChartCopy
```

## pbi visual delete

```bash
pbi visual delete <page> <visual>         # interactive confirmation
pbi visual delete <page> <visual> -f      # skip confirmation
```

## pbi visual group

Group visuals together into a visual group container. The group's bounding box is computed automatically from the children's positions.

```bash
pbi visual group <page> <vis1> <vis2> [vis3 ...] [--name "Group Name"]
```

```bash
pbi visual group "Sales" revenueChart profitChart --name "Revenue Charts"
pbi visual group "Sales" 1 2 3 -n "Top Row"
```

## pbi visual ungroup

Dissolve a visual group, freeing its children as independent visuals.

```bash
pbi visual ungroup <page> <group>
```

```bash
pbi visual ungroup "Sales" "Revenue Charts"
```

## pbi visual sort

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

## pbi visual format

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

## pbi visual column

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

## pbi visual types

Reference for visual types and their data roles.

```bash
pbi visual types                    # all types with role names
pbi visual types scatterChart       # detailed roles for one type
```

## pbi visual props

List all named visual properties with types and descriptions.
