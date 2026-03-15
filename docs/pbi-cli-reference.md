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
pbi page get "Sales Overview"                          # overview with background, visual count
pbi page get "Sales Overview" width displayOption      # specific properties
pbi visual get "Sales Overview" revenueChart --full    # everything in one call
pbi visual get "Sales Overview" revenueChart title.show background.color
pbi visual get "Sales Overview" revenueChart --all-props
pbi visual diff "Sales Overview" revenueChart "Executive Summary" revenueChartCopy
pbi visual page-diff "Sales Overview" "Executive Summary"

# Property writes
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom
pbi page set "Sales Overview" width=1440 displayOption=FitToWidth
pbi visual set "Sales Overview" revenueChart title.show=true title.text="Revenue"

# Batch property writes
pbi page set-all background.color="#F0EDE8"
pbi visual set-all border.show=true --page "Sales Overview" --visual-type slicer
pbi visual set-all columnHeaders.backColor="#162F38" --all-pages --visual-type tableEx
pbi visual set-all border.color="#DDD6CC" --all-pages --where border.color="#EDEBE9"

# Bulk column rename across all pages
pbi visual column "any" "any" Sales.UPN --rename "User Principal Name" --all-pages

# Discovery
pbi map --page "Sales Overview"    # single page detail
pbi map --pages                    # pages only, no model
pbi map --model                    # model only
pbi model relationships            # table relationships
pbi model path Sales Customers     # relationship chain

# Diff and apply
pbi diff sales.yaml                # preview what apply would change
pbi apply sales.yaml --dry-run     # validate
pbi apply sales.yaml               # apply

# Styles (reusable formatting presets)
pbi style create card-style --from-visual "Sales" kpiStrip
pbi style apply "Device Intel" --visual-type cardVisual --style card-style
pbi style list                     # project + global styles
pbi style clone card-style --to-global

# Layout
pbi visual align "Sales" s1 s2 s3 --distribute horizontal --margin 16
pbi visual align "Sales" chart1 chart2 --align top --match-height

# Stateful operations
pbi visual sort set "Sales Overview" revenueChart Sales.Revenue --direction desc
pbi visual format set "Sales Overview" revenueChart dataPoint.fill --mode measure --source Sales.ColorMeasure

# Theme migration
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
| [Themes](themes.md) | Theme apply, export, delete, migrate |
| [Validation](validation.md) | Structural, layout, and relationship validation |
| [Agent Workflows](agent-workflows.md) | Recommended agent workflows |
