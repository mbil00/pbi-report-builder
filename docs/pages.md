# Page Commands

## pbi page list

```bash
pbi page list
```

Table of all pages with index, name, size, display option, visibility, and visual count.

## pbi page get

```bash
pbi page get <page>                    # all properties
pbi page get <page> <property>         # single property value
```

## pbi page set

Supports single property or batch mode:

```bash
pbi page set <page> <property> <value>                          # single (legacy)
pbi page set <page> prop=value [prop=value ...]                  # batch
```

**Properties:**

| Property | Type | Values |
|----------|------|--------|
| `displayName` | string | Any text |
| `width` | number | Pixels |
| `height` | number | Pixels |
| `displayOption` | enum | `FitToPage`, `FitToWidth`, `ActualSize` |
| `visibility` | enum | `AlwaysVisible`, `HiddenInViewMode` |
| `background.color` | color | Page background color (`#hex`) |
| `background.transparency` | number | Background transparency (0-100) |
| `outspace.color` | color | Outspace (area outside canvas) background color |
| `outspace.transparency` | number | Outspace transparency |

```bash
pbi page set "Sales" width=1920
pbi page set "Sales" visibility=HiddenInViewMode
pbi page set "Sales" background.color="#F5F5F5" background.transparency=0
pbi page set "Sales" outspace.color="#E0E0E0"

# Legacy single-property syntax still works
pbi page set "Sales" width 1920
```

## pbi page create

```bash
pbi page create <display-name> [--width 1280] [--height 720] [--display FitToPage]
```

## pbi page copy

Deep-copies a page including all visuals. Each visual gets a new unique ID.

```bash
pbi page copy <source-page> <new-display-name>
```

## pbi page delete

```bash
pbi page delete <page>         # interactive confirmation
pbi page delete <page> -f      # skip confirmation
```

## pbi page props

List all settable page properties with types.

## Page Templates

### pbi page save-template

Save a page's layout and formatting as a reusable template. Captures visual positions, types, and all formatting. Does not capture data bindings, filters, or sort — those are applied separately after applying the template.

```bash
pbi page save-template <page> <template-name>
```

```bash
pbi page save-template "Sales Overview" sales-layout
pbi page save-template "KPI Dashboard" kpi-strip
```

### pbi page apply-template

Apply a saved template to a page. Creates visuals matching the template's layout and formatting. Sets page dimensions and background from the template.

```bash
pbi page apply-template <page> <template-name>
```

```bash
# Create a new page and apply a template
pbi page create "Q2 Sales"
pbi page apply-template "Q2 Sales" sales-layout
```

### pbi page templates

List all available templates.

```bash
pbi page templates
```

### pbi page delete-template

Delete a saved template.

```bash
pbi page delete-template <template-name>
```

Templates are stored in `<project>/.pbi-templates/` as JSON files that can be version-controlled.

## Drillthrough Pages

### pbi page set-drillthrough

Configure a page as a drillthrough target. The page becomes hidden and accepts filter context when users right-click data points on other pages.

```bash
# Single drillthrough field
pbi page set-drillthrough "Product Details" Product.Category

# Multiple fields
pbi page set-drillthrough "Details" Product.Category Region.Country

# Cross-report drillthrough
pbi page set-drillthrough "Shared Details" Product.Category --cross-report
```

### pbi page clear-drillthrough

Remove drillthrough configuration and restore page to normal visibility.

```bash
pbi page clear-drillthrough "Product Details"
```

## Tooltip Pages

### pbi page set-tooltip

Configure a page as a custom tooltip page (shown on hover). Default size is 320x240.

```bash
# Basic tooltip page
pbi page set-tooltip "Sales Tooltip"

# Custom size
pbi page set-tooltip "Sales Tooltip" -W 400 -H 300

# With auto-match fields
pbi page set-tooltip "Sales Tooltip" Product.Category
```

To link a visual to this tooltip page:

```bash
pbi visual set <page> <visual> tooltip.type=ReportPage tooltip.section=<tooltip-page-folder-name>
```

### pbi page clear-tooltip

Remove tooltip configuration from a page.

```bash
pbi page clear-tooltip "Sales Tooltip"
```
