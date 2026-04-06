# Agent Workflows

Guide for AI agents editing Power BI PBIP projects with the `pbi` CLI.

## Concepts

A **report** contains **pages**. Each page contains **visuals** (charts, tables, cards, slicers, shapes, textboxes). Visuals display data through **bindings** that reference fields from the **semantic model** (tables, columns, measures). Visual appearance is controlled by **properties** (position, border, background) and **chart objects** (legend, axes, labels).

Two output formats exist:
- **`pbi map`** — read-only project overview. Includes the data model and all pages. Not editable.
- **`pbi page export`** — editable YAML for use with `pbi apply`. This is the format you write and edit.

## Naming Convention

Name every visual you create (`name:` in YAML or `--name` on create). Unnamed visuals get hex UUIDs which make YAML unreadable and apply non-idempotent. Use short, descriptive names: `revenueChart`, `regionSlicer`, `kpiStrip`.

## Choose Your Approach

| Task | Approach |
|------|----------|
| Understand the project | `pbi map` |
| Understand the data model | `pbi model table list` then `pbi model fields <Table>` |
| Check reusable assets before building | `pbi catalog list --kind ...` |
| Build or restyle a page | `pbi page export` (or write YAML from scratch) then `pbi apply` |
| Redesign a page completely | `pbi page export` then edit then `pbi apply --overwrite` |
| Tweak 1-2 properties quickly | `pbi visual set` (imperative) |
| Apply consistent formatting | Styles: `pbi catalog apply style/...` or `style:` in YAML |
| Reuse a standard page layout | Templates: `pbi catalog apply page/...` |
| Stamp repeated widget groups | Components: `pbi catalog apply component/... --row N` |
| Change theme colors everywhere | `pbi theme migrate old.json new.json` |

**Rule of thumb:** Use `pbi page export` + `pbi apply` for any multi-visual work. Use imperative commands only for quick one-off tweaks.

## The Apply Workflow

This is the primary workflow for building and editing pages.

### 1. Discover

```bash
pbi map                                 # read-only overview: model + all pages
pbi model fields Sales                  # what fields can I bind?
pbi model path Sales Calendar           # how are tables related?
```

Before building visuals from scratch, check the reuse stores for existing assets:

```bash
pbi catalog list --kind style           # saved formatting presets
pbi catalog list --kind component       # saved visual groups
pbi catalog list --kind page            # saved page layouts
```

These stores grow over time. Prefer reusing an existing style, component, or template over building from scratch — it keeps reports consistent and saves work.

### 2. Export (existing page) or write YAML (new page)

```bash
pbi page export "Sales Overview" -o sales.yaml
```

Or write YAML from scratch for a new page:

```yaml
pages:
- name: Sales Overview
  width: 1280
  height: 720
  visuals:
  - name: revenueChart
    type: clusteredBarChart
    position: 16, 80
    size: 600 x 400
    title: { show: true, text: Revenue by Region }
    border: { show: true, radius: 8 }
    bindings:
      Category: Sales.Region
      Y: Sales.TotalRevenue
  - name: regionSlicer
    type: slicer
    position: 640, 80
    size: 300 x 200
    bindings:
      Field: Sales.Region
```

### 3. Preview and apply

```bash
pbi diff sales.yaml                     # see what would change, property by property
pbi apply sales.yaml --dry-run          # validate without writing
pbi apply sales.yaml                    # apply changes
```

### 4. Verify

```bash
pbi validate                            # structural checks (overlaps, out-of-bounds, broken refs)
pbi render "Sales Overview" --screenshot # visual layout mockup as HTML + PNG
```

Repeat steps 2-4 as needed. Apply is idempotent when visuals are named.

### Overwrite mode

`pbi apply --overwrite` deletes visuals on the page that are not in the YAML. The existing page is backed up automatically before overwrite. Use this when the YAML should be the single source of truth.

### Stdin

YAML commands accept stdin: `cat sales.yaml | pbi apply` or `pbi apply -`.

## YAML Features

See [yaml-examples/](yaml-examples/) for copy-paste snippets covering every feature, including a [complete working page](yaml-examples/complete-page.yaml).

The apply YAML supports more than basic properties. These features are **apply-only** and do not appear in `pbi page export` output unless noted.

| Feature | Syntax | Docs |
|---------|--------|------|
| Nested properties | `title: { show: true, text: "Hello" }` | [visuals.md](visuals.md) |
| Chart objects | `chart:legend.show: true` | [visuals.md](visuals.md) |
| Style references | `style: card-style` | [visuals.md](visuals.md) |
| Per-measure formatting | `value.fontSize [Measures.X]: 20` | [visuals.md](visuals.md) |
| Filters | `filters: [{field: X.Y, type: include, values: [...]}]` | [data.md](data.md) |
| Conditional formatting | `conditionalFormatting: {dataPoint.fill: {mode: measure, source: X.Y}}` | [data.md](data.md) |
| Interactions | `interactions: [{source: a, target: b, type: NoFilter}]` | [interactions.md](interactions.md) |
| Bookmarks | `bookmarks: [{name: X, page: Y, hide: [...]}]` | [bookmarks.md](bookmarks.md) |

Note: conditional formatting and bookmarks are **apply-only** (not produced by export).

## Reuse: Styles, Components, Templates

The CLI maintains stores of reusable assets at two scopes: **project** (local to the report) and **global** (`~/.config/pbi/`, shared across all projects). These stores are designed to grow over time into a gallery of proven, reusable building blocks.

**Before building, check the stores.** If a matching style, component, or template exists, use it. If you build something that will be reused, save it back to the store.

| Need | Tool | Scope |
|------|------|-------|
| Same formatting on many visuals | **Style** | Property presets |
| Same multi-visual widget repeated | **Component** | Grouped visuals with parameters |
| Same full page layout reused | **Template** | Entire page with all visuals |

### Styles

```bash
pbi catalog list --kind style
pbi catalog apply style/card-style "Page" --visual myCard

# Save a well-formatted visual as a reusable style
pbi catalog create style --from-visual "Dashboard" --visual kpiCard --name card-style
pbi catalog clone style/card-style --to-global
```

Or reference in YAML: `style: card-style`. See [visuals.md](visuals.md).

### Components

```bash
pbi catalog list --kind component
pbi catalog get component/kpi-widget
pbi catalog apply component/kpi-widget "Dashboard" --x 16 --y 200 --set title=Revenue
pbi catalog apply component/kpi-widget "Dashboard" --row 4 --set-each title=Rev,Margin,Pipeline,Backlog

# Save a visual group you'll reuse
pbi catalog create component --from-visual "Dashboard" --visual "KPI Group" --name kpi-widget
pbi catalog clone component/kpi-widget --to-global
```

Components use `{{ param }}` substitution. See `pbi catalog get component/<name>` for parameters.

### Templates

```bash
pbi catalog list --kind page
pbi catalog apply page/corp-intro "My Intro" --scope global
pbi page create "New Page" --from-template corp-intro --template-global

# Save a page layout you'll reuse
pbi catalog create page --from-visual "Intro Page" --name corp-intro --scope global
```

See [pages.md](pages.md).

## Imperative Commands (Quick Edits)

For one-off changes where YAML is overkill:

```bash
pbi visual set "Sales" chart title.text="Q2 Revenue" border.radius=8
pbi visual move "Sales" chart --x 16 --y 200
pbi visual resize "Sales" chart --width 940 --height 400
pbi visual bind "Sales" chart Values Sales.Revenue
pbi visual arrange align "Sales" s1 s2 s3 --distribute horizontal --margin 16
```

## Bulk Operations

```bash
pbi visual set-all border.show=true --all-pages --visual-type slicer
pbi visual set-all border.color="#DDD6CC" --all-pages --where border.color="#EDEBE9"
pbi visual column "any" "any" Table.Field --rename "Display Name" --all-pages
pbi theme migrate old-theme.json new-theme.json
```

## Reference

| Topic | Command | Docs |
|-------|---------|------|
| Full command reference | `pbi <command> --help` | [pbi-cli-reference.md](pbi-cli-reference.md) |
| Visual properties | `pbi visual properties` | [visuals.md](visuals.md) |
| Page properties | `pbi page properties` | [pages.md](pages.md) |
| Data binding and filters | `pbi visual bind`, `pbi filter create` | [data.md](data.md) |
| Model inspection | `pbi model table list`, `pbi model fields`, `pbi model search` | [model.md](model.md) |
| Themes | `pbi theme apply/migrate` | [themes.md](themes.md) |
| Bookmarks | `pbi bookmark create/set` | [bookmarks.md](bookmarks.md) |
| Interactions | `pbi interaction set` | [interactions.md](interactions.md) |
| Validation | `pbi validate` | [validation.md](validation.md) |
| Layout preview | `pbi render` | [render.md](render.md) |
| Shape presets | `pbi catalog list --kind style` | [visuals.md](visuals.md) |
| Capabilities | `pbi capabilities` | [capabilities.md](capabilities.md) |
