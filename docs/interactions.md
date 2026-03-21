# Interactions & Navigation

## Visual Interactions

```bash
pbi interaction list "Sales Overview"

pbi interaction set "Sales Overview" regionSlicer revenueChart --mode DataFilter
pbi interaction set "Sales Overview" categoryChart detailTable --mode HighlightFilter
pbi interaction set "Sales Overview" dateSlicer kpiCard --mode NoFilter

pbi interaction clear "Sales Overview" regionSlicer revenueChart
pbi interaction clear "Sales Overview" regionSlicer
```

## Button Actions

Use the first-class `pbi nav` helpers for button and shape actions:

```bash
pbi nav set-back "Sales Overview" navButton
pbi nav set-page "Sales Overview" navButton "Overview"
pbi nav set-bookmark "Sales Overview" toggleBtn "Show Details"
pbi nav set-url "Sales Overview" helpBtn "https://docs.example.com"
pbi nav set-drillthrough "Sales Overview" detailsBtn "Product Details"
pbi nav set-tooltip "Sales Overview" revenueChart "Sales Tooltip"
pbi nav clear-tooltip "Sales Overview" revenueChart
pbi nav clear "Sales Overview" helpBtn
```

Optional tooltips can be attached during setup:

```bash
pbi nav set-page "Sales Overview" navButton "Overview" --tooltip "Go to overview"
```

The underlying action properties are still available through `pbi visual set` when you need lower-level control:

```bash
pbi visual set "Sales Overview" navButton action.show=true action.type=Back
pbi visual set "Sales Overview" navButton action.show=true action.type=PageNavigation action.page="Overview"
pbi visual set "Sales Overview" toggleBtn action.show=true action.type=Bookmark action.bookmark="Show Details"
pbi visual set "Sales Overview" detailsBtn action.show=true action.type=Drillthrough action.drillthrough="Product Details"
pbi visual set "Sales Overview" revenueChart tooltip.type=ReportPage tooltip.section="Sales Tooltip"
pbi visual set "Sales Overview" helpBtn action.show=true action.type=WebUrl action.url="https://docs.example.com"
```
