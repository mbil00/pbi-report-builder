# PBI CLI Reference

Canonical reference for the `pbi` command-line tool.

## Core Rules

The CLI now follows one grammar:

1. Targets are positional and come before options. Scope narrowing uses `--page`/`--visual` flags.
2. Generic setters use `key=value` only.
3. Stateful features use `get`, `set`, and `clear`.
4. Mutually exclusive behavior uses `--mode`.
5. Repeated values use repeatable flags such as `--value` and `--row`.
6. Field typing uses `--field-type auto|column|measure`.

## Project Discovery

Every command accepts `-p <path>` or `--project <path>`. Without it, `pbi` walks up from the current directory to find a `.pbip` file.

```bash
pbi info
pbi info --project /path/to/project
pbi info --project ./MyReport.pbip
```

## Recommended Targeting

For deterministic automation, use exact page names and exact visual names. Friendly visual names created with `pbi visual create --name ...` or `pbi visual rename ...` are the recommended references for write commands.

## Common Patterns

```bash
# Property reads
pbi report get layoutOptimization settings.pagesPosition
pbi page get "Sales Overview" width displayOption
pbi visual get "Sales Overview" revenueChart title.show background.color
pbi visual get "Sales Overview" revenueChart title.show tooltip.show --defaults
pbi visual get "Sales Overview" revenueChart --all-props
pbi visual get-page "Sales Overview" --visual-type cardVisual
pbi visual diff "Sales Overview" revenueChart "Executive Summary" revenueChartCopy

# Property writes
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom
pbi page set "Sales Overview" width=1440 displayOption=FitToWidth
pbi visual set "Sales Overview" revenueChart title.show=true title.text="Revenue"

# Batch property writes
pbi page set-all background.color="#F0EDE8"
pbi page set-all background.color="#F0EDE8" --exclude "_"
pbi visual set-all border.show=true --page "Sales Overview" --visual-type slicer
pbi visual set-all columnHeaders.backColor="#162F38" --all-pages --visual-type tableEx

# Discovery with filtering
pbi map --page "Sales Overview"    # single page detail
pbi map --pages                    # pages only, no model
pbi map --model                    # model only

# Stateful operations
pbi visual sort get "Sales Overview" revenueChart
pbi visual sort set "Sales Overview" revenueChart Sales.Revenue --direction desc
pbi visual sort clear "Sales Overview" revenueChart

pbi visual format get "Sales Overview" revenueChart
pbi visual format set "Sales Overview" revenueChart dataPoint.fill --mode measure --source Sales.ColorMeasure
pbi visual format clear "Sales Overview" revenueChart dataPoint.fill

# Theme migration
pbi theme migrate old-theme.json new-theme.json --dry-run
pbi theme migrate old-theme.json new-theme.json
```

## Filters

Scope is inferred from `--page` and `--visual` flags. Default is report level.

```bash
pbi filter list
pbi filter list --page "Sales Overview"
pbi filter list --page "Sales Overview" --visual revenueChart
```

```bash
pbi filter add Product.Category --mode include --value Bikes --value Accessories
pbi filter add Sales.Revenue --page "Sales Overview" --mode range --min 1000 --max 50000
pbi filter add Customers.Region --page "Sales Overview" --visual revenueChart --mode topn --topn 5 --topn-by Sales.TotalRevenue --direction top
pbi filter add Date.Date --mode relative --operator InLast --count 7 --unit Days
pbi filter add --page "Sales Overview" --mode tuple --row "Product.Color=Red,Product.Size=Large"
```

```bash
pbi filter delete Product.Category
pbi filter delete Sales.Revenue --page "Sales Overview"
pbi filter delete Customers.Region --page "Sales Overview" --visual revenueChart
```

## Detailed References

| Topic | File |
|-------|------|
| [Report Commands](report.md) | Report metadata and settings |
| [Page Commands](pages.md) | Page CRUD, templates, drillthrough, tooltip |
| [Visual Commands](visuals.md) | Visual CRUD, styling, grouping, sorting, formatting |
| [Data & Filters](data.md) | Data binding and filters |
| [Semantic Model Commands](model.md) | Model inspection, field formatting, measure/column edits, batch apply |
| [Interactions & Navigation](interactions.md) | Visual interactions and button actions |
| [Bookmarks](bookmarks.md) | Bookmark management |
| [Properties Reference](properties.md) | Visual property catalog |
| [Agent Workflows](agent-workflows.md) | Recommended agent workflows |
