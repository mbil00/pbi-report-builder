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
pbi report annotation get README
pbi report object get resourcePackages
pbi report resource package get RegisteredResources
pbi report resource item get RegisteredResources logo.png
pbi page get "Sales Overview"                          # overview with background, visual count
pbi page get "Sales Overview" width displayOption      # specific properties
pbi visual get "Sales Overview" revenueChart --full    # everything in one call
pbi visual get "Sales Overview" revenueChart title.show background.color
pbi visual get "Sales Overview" revenueChart --all-props
pbi visual diff "Sales Overview" revenueChart "Executive Summary" revenueChartCopy
pbi visual page-diff "Sales Overview" "Executive Summary"

# Property writes
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom
pbi report annotation set README "Owned by BI team"
pbi report object set objects --from-file report-objects.json
pbi report resource package create BrandAssets --type RegisteredResources
pbi report resource item set RegisteredResources logo.png --type Image --name Logo --from-file ./logo.png
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
pbi model get                      # model settings
pbi model set timeIntelligence=off
pbi model table get Date
pbi model table set Date dateTable=Date
pbi model relationship list         # table relationships
pbi model path Sales Customers     # relationship chain

# Diff and apply
pbi diff sales.yaml                # preview what apply would change
pbi apply sales.yaml --dry-run     # validate
pbi apply sales.yaml               # apply
cat sales.yaml | pbi diff          # diff from stdin
cat sales.yaml | pbi apply         # apply from stdin

# Model YAML apply
pbi model apply model.yaml
cat model.yaml | pbi model apply --dry-run
# model.yaml supports model.timeIntelligence and tables.<name>.dateTable

# Styles (reusable formatting presets)
pbi style create card-style --from-visual "Sales" kpiStrip
pbi style apply "Device Intel" --visual-type cardVisual --style card-style
pbi style list                     # project + global styles
pbi style clone card-style --to-global

# Page templates (reusable full-page YAML)
pbi page template create "Sales Overview" sales-layout
pbi page template create "Executive Intro" corp-intro --global
pbi page template list --json
pbi page template get corp-intro --global
pbi page template apply "Landing" corp-intro --global --overwrite
pbi page template clone corp-intro --to-project

# Components (reusable grouped widgets)
pbi component create "Dashboard" "KPI Group" --name kpi-card
pbi component list
pbi component get kpi-card
pbi component apply "Dashboard" kpi-card --x 16 --y 200 --set title=Revenue
pbi component apply "Dashboard" kpi-card --row 4 --x 16 --y 200 --gap 12 \
  --set-each title=Revenue,Margin,Pipeline,Backlog
pbi component clone kpi-card --to-global
pbi component delete kpi-card --force

# Page import and sections
pbi page import --from-project /path/to/other --page "Dashboard" --name "My Dashboard"
pbi page import --from-project /path/to/other --page "Intro" --include-resources
pbi page section create "Dashboard" "Market / Sell" --x 221 --y 130 --width 512 --height 220
pbi page section list "Dashboard"

# Image resources
pbi image create ./logo.png
pbi image list
pbi image prune --force

# Visual tree (group hierarchy)
pbi visual tree "Dashboard"
pbi visual tree "Dashboard" --json

# Navigation helpers
pbi nav page set "Sales Overview" navButton "Executive Summary"
pbi nav bookmark set "Sales Overview" toggleBtn "Show Details"
pbi nav back set "Drillthrough" backButton
pbi nav url set "Sales Overview" helpBtn "https://docs.example.com"
pbi nav drillthrough set "Sales Overview" detailsBtn "Product Details"
pbi nav action get "Sales Overview" helpBtn
pbi nav tooltip set "Sales Overview" revenueChart "Sales Tooltip"
pbi nav tooltip clear "Sales Overview" revenueChart
pbi nav action clear "Sales Overview" helpBtn

# Layout
pbi visual arrange align "Sales" s1 s2 s3 --distribute horizontal --margin 16
pbi visual arrange align "Sales" chart1 chart2 --align top --match-height

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
pbi filter create Product.Category --mode include --value Bikes --value Accessories
pbi filter create Sales.Revenue --page "Sales Overview" --mode range --min 1000 --max 50000
pbi filter create Customers.Region --page "Sales Overview" --visual revenueChart --mode topn --topn 5 --topn-by Sales.TotalRevenue --direction top
pbi filter create Date.Date --mode relative --operator InLast --count 7 --unit Days
pbi filter create --page "Sales Overview" --mode tuple --row "Product.Color=Red,Product.Size=Large"
pbi filter create Product.Name --mode advanced --operator contains --value "Pro"
pbi filter create Product.Name --mode advanced --operator is-blank
pbi filter create Sales.Revenue --mode advanced --operator greater-than --value 1000
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
| [Page Commands](pages.md) | Page CRUD, templates, import, sections, drillthrough, tooltip |
| [Visual Commands](visuals.md) | Visual CRUD, styling, grouping, tree view, sorting, formatting |
| [Data & Filters](data.md) | Data binding and filters |
| [Semantic Model Commands](model.md) | Model inspection, field formatting, measure/column edits, batch apply |
| [Interactions & Navigation](interactions.md) | Visual interactions and button actions |
| [Bookmarks](bookmarks.md) | Bookmark management |
| [Properties Reference](properties.md) | Visual property catalog |
| [Themes](themes.md) | Theme apply, export, delete, migrate |
| [Validation](validation.md) | Structural, layout, and relationship validation |
| [Agent Workflows](agent-workflows.md) | Recommended agent workflows (includes components, sections, images) |
