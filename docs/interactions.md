# Interactions & Navigation

## Visual Interactions

Control how visuals cross-filter, cross-highlight, or ignore each other's selections. By default, Power BI applies `DataFilter` for most visual types. Custom interactions override this per source-target pair.

### pbi interaction list

```bash
pbi interaction list <page>
```

Shows all custom interactions on a page. If no custom interactions exist, all visuals use default behavior.

### pbi interaction set

```bash
pbi interaction set <page> <source> <target> <type>
```

**Interaction types:**

| Type | Description |
|------|-------------|
| `DataFilter` | Selection in source filters the target |
| `HighlightFilter` | Selection in source highlights matching data in the target |
| `NoFilter` | Target ignores selections from the source |
| `Default` | Use default behavior for the target visual type |

```bash
# Make a slicer filter a chart
pbi interaction set "Sales" regionSlicer revenueChart DataFilter

# Highlight instead of filter
pbi interaction set "Sales" categoryChart detailTable HighlightFilter

# Prevent a visual from reacting to slicer
pbi interaction set "Sales" dateSlicer kpiCard NoFilter

# Reset to default behavior
pbi interaction set "Sales" regionSlicer revenueChart Default
```

### pbi interaction remove

Remove custom interactions. Omit the target to remove all interactions from a source.

```bash
pbi interaction remove <page> <source>                   # remove all from source
pbi interaction remove <page> <source> <target>          # remove specific pair
```

```bash
pbi interaction remove "Sales" regionSlicer revenueChart
pbi interaction remove "Sales" regionSlicer              # remove all from this slicer
```

## Button Actions

Button actions are configured via `visual set` using `action.*` properties. They apply to `actionButton` visuals.

```bash
pbi visual create "Sales" actionButton -n navButton --x 1800 --y 20 -W 100 -H 40
```

### Action Types

| Type | Description | Key Property |
|------|-------------|-------------|
| `Back` | Navigate back to the previous page | — |
| `Bookmark` | Apply a bookmark | `action.bookmark` |
| `Drillthrough` | Navigate to a drillthrough page | `action.drillthrough` |
| `PageNavigation` | Navigate to a specific page | `action.page` |
| `QnA` | Open Q&A | — |
| `WebUrl` | Open a URL | `action.url` |

### Action Properties

| Property | Type | Description |
|----------|------|-------------|
| `action.show` | boolean | Enable button action |
| `action.type` | string | Action type (see above) |
| `action.bookmark` | string | Target bookmark name |
| `action.page` | string | Target page name |
| `action.drillthrough` | string | Target drillthrough page |
| `action.url` | string | Target URL |
| `action.tooltip` | string | Button tooltip text |

### Examples

```bash
# Back button
pbi visual set "Sales" navButton action.show=true action.type=Back action.tooltip="Go Back"

# Page navigation
pbi visual set "Sales" navButton action.show=true action.type=PageNavigation action.page="Overview"

# Bookmark toggle
pbi visual set "Sales" toggleBtn action.show=true action.type=Bookmark action.bookmark="Show Details"

# Web link
pbi visual set "Sales" helpBtn action.show=true action.type=WebUrl action.url="https://docs.example.com"

# Drillthrough
pbi visual set "Sales" drillBtn action.show=true action.type=Drillthrough action.drillthrough="Product Details"
```
