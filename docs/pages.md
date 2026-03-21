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
pbi page create "Overview" --from-template intro-page
pbi page create "Overview" --from-template corp-intro --template-global
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
pbi page template create "Sales Overview" sales-layout
pbi page template create "Executive Intro" corp-intro --global --description "Shared intro page"

pbi page template list
pbi page template list --global
pbi page template list --json
pbi page template get sales-layout
pbi page template get corp-intro --global

pbi page template apply "Q2 Sales" sales-layout
pbi page template apply "Landing" corp-intro --global --overwrite
pbi page template apply "Landing" corp-intro --global --dry-run

pbi page template clone corp-intro --to-project
pbi page template clone sales-layout --to-global

pbi page template delete sales-layout
pbi page template delete corp-intro --global
```

Page templates are now full reusable page definitions backed by apply-compatible YAML.

Key template behaviors:
- Project templates live under `.pbi-templates/`
- Global templates live under `~/.config/pbi/templates/`
- Resolution is project first, then global fallback
- Applying a template updates the target page to match the template; use `--overwrite` to remove visuals not present in the template
- Templates can include visuals, bindings, filters, interactions, and page-local bookmarks

## Import (Cross-Project)

```bash
# Copy a page from another project
pbi page import --from-project "/path/to/QBR Report" --page "Divisional Dashboard" \
  --name "My Dashboard"

# Also copy image resources used by the page
pbi page import --from-project "/path/to/other" --page "Introduction" \
  --include-resources
```

Import copies the entire page directory, regenerates all visual and page IDs, and fixes group references (parentGroupName). Use `--include-resources` to also copy image files from `RegisteredResources/` and register them in the target project.

## Sections

```bash
# Create a section with background shape and title textbox
pbi page section create "Dashboard" "Market / Sell" \
  --x 221 --y 130 --width 512 --height 220 \
  --background "#F5F5F5" --radius 10 \
  --title-color "#002C77" --title-font "DIN" --title-size 14

# List sections on a page
pbi page section list "Dashboard"
```

Each section creates a shape visual (background), a textbox visual (title), and groups them together. Customizable via `--background`, `--radius`, `--title-color`, `--title-font`, `--title-size`.

## Drillthrough

```bash
pbi page drillthrough set "Product Details" Product.Category
pbi page drillthrough get "Product Details"
pbi page drillthrough set "Shared Details" Product.Category --cross-report
pbi page drillthrough set "Visible Details" Product.Category --no-hide
pbi page drillthrough clear "Product Details"
```

`page drillthrough set` hides the page in view mode by default because that is
the common Desktop pattern for drillthrough targets. Use `--no-hide` when you
want the page to stay visible in normal navigation.

## Tooltip

```bash
pbi page tooltip set "Sales Tooltip"
pbi page tooltip get "Sales Tooltip"
pbi page tooltip set "Sales Tooltip" Product.Category --width 400 --height 300
pbi page tooltip clear "Sales Tooltip"
```

To link a visual to a tooltip page:

```bash
pbi nav tooltip set "Sales Overview" revenueChart "Sales Tooltip"
```

To wire a drillthrough button:

```bash
pbi nav drillthrough set "Sales Overview" detailsBtn "Product Details"
```
