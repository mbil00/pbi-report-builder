# Agent Workflows

Shortest path to reliable PBIR changes. Prefer declarative YAML over imperative commands.

## Choose Your Workflow

| Task | Approach |
|------|----------|
| Build a new page | Write YAML + `pbi apply` |
| Restyle / restructure a page | `pbi page export` → edit YAML → `pbi apply` |
| Redesign a page completely | `pbi page export` → edit YAML → `pbi apply --overwrite` |
| Reuse a standard intro/info/detail page | `pbi page template apply` |
| Stamp repeated composite widgets | `pbi component create` → `pbi component apply --row N` |
| Import a page from another project | `pbi page import --from-project ... --page ...` |
| Add page section backgrounds | `pbi page section create` |
| Tweak 1-2 properties | `pbi visual set` (imperative) |
| Apply consistent formatting | `pbi style apply` or `style:` in YAML |
| Apply a built-in shape preset | `pbi style apply --style rounded-container` |
| Change a theme's colors everywhere | `pbi theme migrate old.json new.json` |
| Manage embedded images | `pbi image create` / `pbi image prune` |
| Understand group hierarchy | `pbi visual tree "Page"` |
| Preview a page layout visually | `pbi render "Page" --screenshot` |

**Rule of thumb:** For any page-level work, start with `pbi page export`. Use imperative commands only for quick one-off tweaks.

## Discovery (Before You Build)

Understand what exists before writing anything:

```bash
pbi info                              # tree view of pages and visuals
pbi page list                         # page table with sizes and counts
pbi page get "Page Name"              # page properties, background, visual count
pbi visual list "Page Name"           # visual table with positions and types
pbi visual tree "Page Name"           # group hierarchy as a tree
pbi visual get "Page" visual --full   # everything: props, objects, columns, filters, sort
pbi model table list                  # semantic model tables
pbi model fields TableName            # columns + measures for binding
pbi model relationship list           # table relationships (verify cross-table joins)
pbi model path TableA TableB          # relationship chain between two tables
```

For an existing page you want to modify:

```bash
pbi page export "Sales Overview" -o sales.yaml
```

This gives you the complete YAML spec — position, size, styling, bindings, column widths, display names, filters, sort, interactions, and the raw `pbir` block for full fidelity.

## The Apply Workflow (Preferred)

`pbi apply` creates, styles, binds, and positions visuals from a declarative YAML file in a single command.

YAML commands accept stdin as well as file paths. You can use `-` or pipe generated/templated YAML straight into `pbi apply`, `pbi diff`, or `pbi model apply`.

### Export → Edit → Apply

```bash
pbi page export "Sales Overview" -o sales.yaml   # capture current state
# edit sales.yaml (change what you need)
pbi diff sales.yaml                               # preview changes property-by-property
pbi apply sales.yaml --dry-run                    # validate
pbi apply sales.yaml                              # apply
cat sales.yaml | pbi apply --dry-run              # stdin works too
pbi validate                                      # check layout + structure
```

Common YAML edits:
- Reposition/resize visuals (`position` / `size`)
- Change titles, colors, borders (inline properties)
- Swap bindings (field references under `bindings`)
- Add/remove visuals (append to or delete from `visuals` list; use `--overwrite` for deletions)
- Duplicate a visual (copy a YAML block, change the `name`)
- Restyle everything (find-and-replace a color)

### Interactions and Bookmarks in YAML

Instead of running 20+ imperative `pbi interaction set` commands, declare them in the YAML:

```yaml
pages:
- name: Sales Overview
  interactions:
  - source: slicerRegion
    target: revenueChart
    type: DataFilter
  - source: kpiStrip
    target: revenueChart
    type: NoFilter
  visuals: [...]

bookmarks:
- name: Minimal View
  page: Sales Overview
  hide: [detailTable, footnote]
```

### Conditional Formatting in YAML

```yaml
conditionalFormatting:
  dataPoint.fill:
    mode: measure
    source: Measures.ComplianceColor
  values.fontColor:
    mode: gradient
    source: Sales.Revenue
    min: { color: "#FF0000", value: 0 }
    max: { color: "#00FF00", value: 100 }
```

### Filters in YAML

```yaml
filters:
- field: Product.Category
  type: include
  values: [Bikes, Accessories]
- field: Devices.Manufacturer
  type: topN
  count: 15
  by: Measures Table.Total Devices
- field: Sales.Revenue
  type: range
  min: 1000
  max: 50000
- field: Product.Name
  type: advanced
  operator: contains
  value: Pro
- field: Product.Description
  type: advanced
  operator: is-not-blank
```

## Styles (Reusable Formatting)

Styles save formatting as named presets. Use them to keep visuals consistent across pages without repeating property lists.

### Capture a style from an existing visual

```bash
pbi style create card-style --from-visual "Executive Overview" --visual kpiStrip
```

### Apply a style

```bash
# To one visual
pbi style apply "Device Intelligence" kpiStrip --style card-style

# To all visuals of a type on a page
pbi style apply "Device Intelligence" --visual-type cardVisual --style card-style

# In YAML — just reference the style name
- name: kpiStrip
  type: cardVisual
  style: card-style
  bindings: { ... }
```

### Global styles (shared across projects)

```bash
pbi style create card-style ... --global        # save to ~/.config/pbi/styles/
pbi style clone card-style --to-project         # copy global → project
pbi style clone card-style --to-global          # copy project → global
pbi style list                                  # shows both scopes
```

Style resolution: project-scoped styles take priority, global styles are the fallback.

## Page Templates (Reusable Full Pages)

Page templates now store full apply-compatible page YAML, not just stripped layout shells. Use them for intro pages, landing pages, info pages, repeated detail layouts, and other reusable report sections.

```bash
# Save one page as a reusable template
pbi page template create "Executive Intro" corp-intro --global --description "Shared intro page"

# Discover available templates
pbi page template list
pbi page template list --global
pbi page template list --json
pbi page template get corp-intro --global

# Reuse a template on a new or existing page
pbi page create "Intro" --from-template corp-intro --template-global
pbi page template apply "Overview" corp-intro --global
pbi page template apply "Overview" corp-intro --global --overwrite
```

Template resolution matches styles: project templates win, global templates are the fallback.

Templates can carry:
- page size and page properties
- visuals and bindings
- filters and interactions
- page-local bookmarks

Use `--overwrite` on `page template apply` when the target page should be reconciled exactly to the template.

## Components (Reusable Grouped Widgets)

Components sit between styles (one visual) and templates (entire page). They capture a group of visuals with relative positions, formatting, bindings, filters, and parameterizable fields.

### Save a component from an existing group

```bash
pbi component create "Dashboard" "KPI: Revenue" --name kpi-card-with-py \
  --description "KPI gauge with prior year value and rounded container"
# Saves 4 visuals with auto-detected parameters (title, filters)
```

### Stamp onto a page

```bash
pbi component apply "Dashboard" kpi-card-with-py --x 16 --y 200 \
  --set title="Compliance Rate" \
  --set "filter[DimFacts.Kpi Name]=Compliance Rate"
```

### Batch stamp a row of instances

```bash
pbi component apply "Dashboard" kpi-card-with-py \
  --row 4 --x 16 --y 200 --gap 12 \
  --set-each title=Revenue,Margin,Pipeline,Backlog \
  --set-each "filter[DimFacts.Kpi Name]=Revenue,Margin,Pipeline,Backlog"
```

### Manage components

```bash
pbi component list
pbi component get kpi-card-with-py
pbi component clone kpi-card-with-py --to-global
pbi component delete kpi-card-with-py --force
```

Component storage mirrors styles: project in `.pbi-components/`, global in `~/.config/pbi/components/`. Parameters use `{{ name }}` syntax in the saved YAML and are substituted at stamp time via `--set`.

## Page Sections

Create section backgrounds (shape + title textbox, grouped) in one command:

```bash
pbi page section create "Dashboard" "Market / Sell" \
  --x 221 --y 130 --width 512 --height 220 \
  --background "#F5F5F5" --radius 10 \
  --title-color "#002C77" --title-font "DIN" --title-size 14

pbi page section list "Dashboard"
```

## Page Import (Cross-Project)

Copy a page from another PBIP project:

```bash
pbi page import --from-project "/path/to/QBR Report" --page "Divisional Dashboard" \
  --name "My Dashboard"

# Also copy image resources used by the page
pbi page import --from-project "/path/to/other" --page "Introduction" \
  --include-resources
```

Import regenerates all visual IDs and fixes group references automatically.

## Image Resources

Manage embedded images (logos, banners) in `RegisteredResources/`:

```bash
pbi image create ./company-logo.png        # register an image file
pbi image list                              # list with sizes and reference counts
pbi image prune --force                     # remove unreferenced images
```

## Shape Presets (Bundled Styles)

Four built-in shape style presets ship with the tool, always available by name:

| Preset | Description |
|--------|-------------|
| `rounded-container` | Filled rounded rect with shadow — KPI card background |
| `section-bg` | Subtle fill for page section zoning |
| `separator` | Thin horizontal/vertical line |
| `card-frame` | Transparent with border only |

```bash
# Use in imperative commands
pbi style apply "Dashboard" bgShape --style rounded-container

# Use in YAML
- name: bgShape
  type: shape
  style: rounded-container

# List bundled presets
pbi style list --bundled
```

## Bulk Operations

```bash
# Set properties across all pages
pbi visual set-all border.show=true border.radius=4 --all-pages --visual-type slicer

# Set properties only where a value matches
pbi visual set-all border.color="#DDD6CC" --all-pages --where border.color="#EDEBE9"

# Rename a column everywhere
pbi visual column "any" "any" DevicesWithPrimaryUser.UPN --rename "User Principal Name" --all-pages

# Migrate all per-visual overrides when changing themes
pbi theme migrate old-theme.json new-theme.json --dry-run
pbi theme migrate old-theme.json new-theme.json
```

## Imperative Commands (Quick Edits)

```bash
pbi visual set "Sales" chart title.text="Q2 Revenue" border.radius=8
pbi visual move "Sales" chart --x 16 --y 200
pbi visual resize "Sales" chart --width 940 --height 400
pbi visual bind "Sales" chart Values Sales.Revenue
pbi visual arrange align "Sales" s1 s2 s3 s4 --distribute horizontal --margin 16
pbi visual arrange align "Sales" chart1 chart2 --align top --match-height
pbi nav set-page "Sales" nextBtn "Details"
pbi nav set-bookmark "Sales" toggleBtn "Minimal View"
```

## Preview (Layout Mockups)

Render a page as an HTML mockup to visually verify layout before publishing:

```bash
pbi render "Dashboard" -o dashboard.html              # HTML only
pbi render "Dashboard" -o dashboard.html --screenshot  # HTML + PNG
```

The mockup shows pixel-accurate positions, sizes, backgrounds, borders, text content, and titles. Data visuals appear as labeled placeholders with their bound field names. Useful for reviewing layout changes after `pbi apply` without opening Power BI.

## Validation

Run after any structural changes:

```bash
pbi validate
```

Checks:
- JSON structure and required fields
- Page order consistency
- Visual interaction references
- Bookmark schema compliance
- **Layout issues** — overlapping visuals, out-of-bounds, zero-size
- **Relationship gaps** — cross-table bindings without a relationship path
- **Schema validation** — invalid object names or property names per visual type (with fuzzy suggestions)

## Naming Strategy

Name visuals early (`name:` in YAML or `--name` on create). Friendly names make commands deterministic, exports readable, and applies idempotent.
