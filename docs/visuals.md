# Visual Commands

## Inspect

```bash
pbi visual list "Sales Overview"
pbi visual tree "Sales Overview"              # group hierarchy as a tree
pbi visual tree "Sales Overview" --json       # tree as JSON
pbi visual get "Sales Overview" revenueChart
pbi visual get "Sales Overview" revenueChart title.show background.color
pbi visual get "Sales Overview" revenueChart --all-props
pbi visual get "Sales Overview" revenueChart title.show tooltip.show --defaults
pbi visual get-page "Sales Overview"
pbi visual get-page "Sales Overview" --visual-type cardVisual --all-props
pbi visual diff "Sales Overview" revenueChart "Executive Summary" revenueChartCopy
pbi visual get "Sales Overview" revenueChart --full    # everything: props, objects, columns, filters, sort
pbi visual get "Sales Overview" revenueChart --raw
pbi visual properties
pbi visual properties --visual-type clusteredColumnChart
pbi visual properties --match dropShadow --show-aliases
```

`pbi visual tree` renders the group hierarchy with nested children, showing type, position, size, and hidden state — essential for understanding complex pages with 100+ visuals.

`pbi visual get-page` lists explicit properties across every visual on a page.
Use `--all-props` when you also want core state such as geometry and hidden
flags. `pbi visual diff` compares two visuals and reports only the differing
explicit properties. `pbi visual page-diff` compares two pages (visual counts, shared/unique visuals, property differences).

`pbi visual get --defaults` resolves effective values using explicit settings
plus the CLI's known defaults for common properties, and marks each row as
`explicit` or `default`.

## Set Properties

```bash
pbi visual set "Sales Overview" revenueChart title.show=true title.text="Revenue"
pbi visual set "Sales Overview" revenueChart background.color="#FFFFFF" border.show=true
pbi visual set "Sales Overview" revenueChart accentBar.color="#E8A83E" --for-measure "Sum(Devices.StaleDevices30d)"
```

`pbi visual set` accepts `key=value` only.

## Bulk Styling

```bash
pbi visual set-all background.show=true background.color="#FFFFFF" --page "Sales Overview"
pbi visual set-all border.radius=4 border.show=true --page "Sales Overview" --visual-type slicer
pbi visual set-all background.show=true --page "Sales Overview" --dry-run

# Apply across ALL pages at once
pbi visual set-all columnHeaders.backColor="#162F38" --all-pages --visual-type tableEx
pbi visual set-all border.show=true border.radius=4 --all-pages
```

Use `--page` to target a single page, or `--all-pages` for the entire report. Combine with `--visual-type` to target specific visual types. Use `--where prop=value` to only affect visuals where a property currently matches:

```bash
pbi visual set-all border.color="#DDD6CC" --all-pages --where border.color="#EDEBE9"
```

## CRUD

```bash
pbi visual create "Sales Overview" clusteredColumnChart --name revenueChart --width 600 --height 400
pbi visual create "Sales Overview" card --name kpiCard --title "Total Revenue"
pbi visual create "Sales Overview" clusteredColumnChart --name revenueChart \
  --bind Category=Date.Month --bind Y=Sales.Revenue --sort Date.Month
pbi visual create "Sales Overview" clusteredColumnChart --name revenueChart \
  --bind Category=Date.Month --bind Y=Sales.Revenue --preset chart
pbi visual create "Sales Overview" tableEx --name detailTable --bind Values=Product.Category
pbi visual create "Sales Overview" slicer --name yearSlicer --bind Values=Date.Year --preset slicer
pbi visual move "Sales Overview" revenueChart --x 40 --y 80
pbi visual resize "Sales Overview" revenueChart --width 720 --height 420
pbi visual resize "Sales Overview" revenueChart --height 300           # width unchanged
pbi visual resize "Sales Overview" revenueChart --width 500            # height unchanged
pbi visual copy "Sales Overview" revenueChart --to-page "Executive Summary" --name revenueChartCopy
pbi visual rename "Sales Overview" revenueChart revenueByCategory
pbi visual delete "Sales Overview" revenueChart --force
```

`pbi visual create` now supports repeatable `--bind Role=Table.Field` plus
`--sort Table.Field`, so common visuals can be scaffolded and made usable in one
command. For common types, width and height also default to more practical
authoring sizes than the generic `300 x 200`. Use `--preset` for a better
starting format on supported families:

- `chart` for bar/column/line/combo charts
- `table` for table and matrix
- `slicer` for slicers
- `card` for card visuals

When `--sort` is omitted, builder-aware create also uses semantic-model metadata
to infer a default ascending sort for chart categories and slicer values when
the bound column has `sortByColumn` metadata. Use `--no-auto-sort` to disable
that inference.

## Layout Helpers

```bash
pbi visual arrange row "Sales Overview" card1 card2 card3 --x 40 --y 80 --gap 16
pbi visual arrange column "Sales Overview" slicer1 slicer2 slicer3 --x 24 --y 120 --gap 12
pbi visual arrange grid "Sales Overview" card1 card2 card3 card4 --columns 2 --x 40 --y 80 --column-gap 16 --row-gap 24
```

## Alignment

```bash
pbi visual arrange align "Sales Overview" s1 s2 s3 s4 --distribute horizontal --margin 16
pbi visual arrange align "Sales Overview" chart1 chart2 --align top
pbi visual arrange align "Sales Overview" chart1 chart2 --align left --match-height
pbi visual arrange align "Sales Overview" card1 card2 card3 --align center-x
```

Options: `--align` (left, right, top, bottom, center-x, center-y), `--distribute` (horizontal, vertical), `--match-width`, `--match-height`, `--margin`.

## Grouping

```bash
pbi visual group "Sales Overview" revenueChart profitChart --name "Revenue Charts"
pbi visual ungroup "Sales Overview" "Revenue Charts"
```

## Style Copy

```bash
pbi visual paste-style "Sales Overview" revenueChart profitChart
pbi visual paste-style "Sales Overview" revenueChart profitChart --scope container
pbi visual paste-style "Sales Overview" revenueChart targetChart --to-page "Executive Summary" --scope chart
pbi visual paste-style "Sales Overview" revenueChart --to-page "Executive Summary" --visual-type cardVisual
```

## Sorting

```bash
pbi visual sort get "Sales Overview" revenueChart
pbi visual sort set "Sales Overview" revenueChart Sales.Revenue --direction desc --field-type auto
pbi visual sort set "Sales Overview" revenueChart Product.Category --direction asc --field-type column
pbi visual sort clear "Sales Overview" revenueChart
```

## Conditional Formatting

```bash
pbi visual format get "Sales Overview" revenueChart

pbi visual format set "Sales Overview" revenueChart dataPoint.fill \
  --mode measure \
  --source Sales.ColorMeasure

pbi visual format set "Sales Overview" revenueChart dataPoint.fill \
  --mode gradient \
  --source Sales.Revenue \
  --min-color "#FF0000" --min-value 0 \
  --max-color "#00FF00" --max-value 100

pbi visual format clear "Sales Overview" revenueChart dataPoint.fill
```

## Data Roles

```bash
pbi visual bind "Sales Overview" revenueChart Category Product.Category --field-type auto
pbi visual bind "Sales Overview" revenueChart Y Sales.TotalRevenue --field-type measure
pbi visual unbind "Sales Overview" revenueChart Y
pbi visual bindings "Sales Overview" revenueChart
pbi visual types
pbi visual types clusteredColumnChart
```

## Field Labels

```bash
pbi visual column "Sales Overview" detailTable Product.Category --rename "Category"
pbi visual column "Sales Overview" executiveCard Sales.TotalRevenue --rename "Revenue"

# Bulk rename across all pages
pbi visual column "any" "any" DevicesWithPrimaryUser.UPN --rename "User Principal Name" --all-pages
```

`pbi visual column --rename` works on projection-backed visuals, not just
table-style visuals. Use `--all-pages` to rename a field everywhere at once.
Width and per-field formatting options are still mainly useful on table and matrix visuals.
