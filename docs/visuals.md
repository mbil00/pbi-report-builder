# Visual Commands

## Inspect

```bash
pbi visual list "Sales Overview"
pbi visual get "Sales Overview" revenueChart
pbi visual get "Sales Overview" revenueChart title.show background.color
pbi visual get "Sales Overview" revenueChart --raw
pbi visual properties
pbi visual properties --visual-type clusteredColumnChart
```

## Set Properties

```bash
pbi visual set "Sales Overview" revenueChart title.show=true title.text="Revenue"
pbi visual set "Sales Overview" revenueChart background.color="#FFFFFF" border.show=true
pbi visual set "Sales Overview" revenueChart accentBar.color="#E8A83E" --for-measure "Sum(Devices.StaleDevices30d)"
```

`pbi visual set` accepts `key=value` only.

## Bulk Styling

```bash
pbi visual set-all "Sales Overview" background.show=true background.color="#FFFFFF"
pbi visual set-all "Sales Overview" border.radius=4 border.show=true --visual-type slicer
pbi visual set-all "Sales Overview" background.show=true --dry-run
```

## CRUD

```bash
pbi visual create "Sales Overview" clusteredColumnChart --name revenueChart --width 600 --height 400
pbi visual copy "Sales Overview" revenueChart --to-page "Executive Summary" --name revenueChartCopy
pbi visual rename "Sales Overview" revenueChart revenueByCategory
pbi visual delete "Sales Overview" revenueChart --force
```

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
