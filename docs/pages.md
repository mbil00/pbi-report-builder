# Page Commands

## Metadata

```bash
pbi page list
pbi page get "Sales Overview"
pbi page get "Sales Overview" width displayOption
pbi page set "Sales Overview" width=1440 height=900 displayOption=FitToWidth
pbi page properties
```

Page mutation uses `key=value` only.

## Page Order & Active Page

```bash
pbi page set-active "Sales Overview"
pbi page reorder "Sales Overview" "Executive Summary" "Details"
pbi page reorder "Sales Overview"   # moves Sales Overview to front, others keep order
```

`reorder` accepts a full or partial list. If partial, listed pages move to front and remaining pages keep their current order.

## CRUD

```bash
pbi page create "Sales Overview" --width 1440 --height 900 --display-option FitToWidth
pbi page copy "Sales Overview" "Sales Overview Copy"
pbi page delete "Sales Overview" --force
```

## Export / Apply

```bash
pbi page export
pbi page export "Sales Overview"
pbi page export "Sales Overview" --output sales-overview.yaml

pbi apply sales-overview.yaml
pbi apply sales-overview.yaml --page "Sales Overview"
pbi apply sales-overview.yaml --dry-run
pbi apply sales-overview.yaml --overwrite
```

`pbi page export` emits apply-compatible YAML for both page metadata and visuals,
including tooltip/drillthrough page binding metadata when present.

## Templates

```bash
pbi page save-template "Sales Overview" sales-layout
pbi page apply-template "Q2 Sales" sales-layout
pbi page templates
pbi page delete-template sales-layout
```

## Drillthrough

```bash
pbi page drillthrough set "Product Details" Product.Category
pbi page drillthrough set "Shared Details" Product.Category --cross-report
pbi page drillthrough clear "Product Details"
```

## Tooltip

```bash
pbi page tooltip set "Sales Tooltip"
pbi page tooltip set "Sales Tooltip" Product.Category --width 400 --height 300
pbi page tooltip clear "Sales Tooltip"
```

To link a visual to a tooltip page:

```bash
pbi visual set "Sales Overview" revenueChart tooltip.type=ReportPage tooltip.section=<tooltip-page-folder-name>
```
