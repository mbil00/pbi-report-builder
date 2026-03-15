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

## Batch Updates

```bash
pbi page set-all background.color="#F0EDE8"                    # all pages
pbi page set-all background.color="#F0EDE8" --exclude "_"      # skip pages with "_" in the name
pbi page set-all width=1920 height=1080 --dry-run              # preview changes
```

`pbi page set-all` applies properties to every page in the project. Use `--exclude` to skip pages whose display name contains a given substring (e.g. hidden pages prefixed with `_`).

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
cat sales-overview.yaml | pbi apply --dry-run
cat sales-overview.yaml | pbi diff
```

`pbi page export` emits apply-compatible YAML for both page metadata and visuals,
including tooltip/drillthrough page binding metadata when present.

`pbi apply` and `pbi diff` also accept `-` to read YAML from stdin explicitly.

Key apply behaviors:
- **Additive by default** — only visuals in the YAML are touched
- **`--overwrite`** — full reconciliation: visuals not in YAML are deleted (with backup). Deleted visuals are reported in the output
- **`--dry-run`** — previews all changes including visuals that would be created on new pages and visuals that would be deleted in overwrite mode
- **Visual type conversion** — if a YAML visual specifies an existing `id` but a different `type`, the old visual is deleted and recreated with the new type

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
