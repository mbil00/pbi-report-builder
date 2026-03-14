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

Button actions are configured through `pbi visual set`:

```bash
pbi visual set "Sales Overview" navButton action.show=true action.type=Back
pbi visual set "Sales Overview" navButton action.show=true action.type=PageNavigation action.page="Overview"
pbi visual set "Sales Overview" toggleBtn action.show=true action.type=Bookmark action.bookmark="Show Details"
pbi visual set "Sales Overview" helpBtn action.show=true action.type=WebUrl action.url="https://docs.example.com"
```
