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

Generate a human-readable YAML index that resolves all hex IDs and shows the full hierarchy: Page → Group → Visual → Role → Field. Every entry includes a relative file path.

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

pages:
  - name: Sales Overview  # active
    id: page1
    path: Report.Report/definition/pages/page1
    size: 1920 x 1080
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

```bash
pbi page set "Sales" width 1920
pbi page set "Sales" visibility HiddenInViewMode
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
pbi visual get <page> <visual>                  # overview with formatting and bindings
pbi visual get <page> <visual> <property>        # single property value
pbi visual get <page> <visual> --raw             # full JSON
```

### pbi visual set

```bash
pbi visual set <page> <visual> <property> <value>
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
| `background.color` | color | Background color (`#hex`) |
| `background.transparency` | number | 0–100 |
| `border.show` | boolean | Show border |
| `border.color` | color | Border color |
| `border.width` | number | Border width |
| `border.radius` | number | Corner radius |
| `title.text` | string | Title text |
| `title.show` | boolean | Show title |
| `title.color` | color | Title font color |
| `title.fontSize` | number | Title font size |
| `title.fontFamily` | string | Title font family |
| `title.alignment` | enum | `left`, `center`, `right` |
| `subtitle.text` | string | Subtitle text |
| `subtitle.show` | boolean | Show subtitle |
| `subtitle.color` | color | Subtitle font color |
| `subtitle.fontSize` | number | Subtitle font size |
| `padding.top` | number | Top padding |
| `padding.bottom` | number | Bottom padding |
| `padding.left` | number | Left padding |
| `padding.right` | number | Right padding |
| `shadow.show` | boolean | Show drop shadow |
| `shadow.color` | color | Shadow color |
| `shadow.transparency` | number | Shadow transparency |
| `shadow.position` | string | Shadow position |

Any property not listed above can be accessed via raw JSON dot-path (e.g. `visual.objects.legend`).

```bash
pbi visual set "Sales" chart background.color "#FFFFFF"
pbi visual set "Sales" chart border.show true
pbi visual set "Sales" chart title.text "Revenue by Category"
pbi visual set "Sales" chart title.alignment center
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
    objects             — visual-specific formatting
    visualContainerObjects — container formatting (background, border, title, ...)
  }
  isHidden       — visibility flag
  parentGroupName — group membership (if grouped)
}
```
