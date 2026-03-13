# PBI CLI Reference

Complete reference for the `pbi` command-line tool. All commands operate on Power BI PBIP projects using the PBIR (Enhanced Report Format).

## Project Discovery

Every command accepts `-p <path>` to specify the project. Without it, `pbi` walks up from the current directory to find a `.pbip` file.

```bash
pbi info                          # auto-detect from cwd
pbi info -p /path/to/project      # explicit path
pbi info -p ./MyReport.pbip       # point to .pbip file directly
```

## Referencing Pages and Visuals

Pages and visuals are resolved in this order:

| Method | Example | Notes |
|--------|---------|-------|
| Display name | `"Sales Overview"` | Case-insensitive |
| Partial name | `"Sales"` | Must be unambiguous |
| Folder/ID | `page1`, `a1b2c3d4e5...` | Internal hex ID |
| Index | `1`, `2`, `3` | 1-based, from list order |
| Visual type | `card`, `slicer` | Only if unique on the page |
| Friendly name | `revenueChart` | Set via `visual create --name` or `visual rename` |

## Commands

### pbi info

Tree view of the entire project — pages, visuals, positions, sizes.

```bash
pbi info
```

### pbi map

Generate a human-readable YAML index that resolves all hex IDs and shows the full hierarchy: Page -> Group -> Visual -> Role -> Field. Includes filters at all levels, sort definitions, key chart formatting, and conditional formatting. Every entry includes a relative file path.

```bash
pbi map                     # stdout
pbi map -o pbi-map.yaml     # write to file
```

Output structure:

```yaml
model:
  Product:
    columns: [Category, Sub Category, Color]
    hidden:  [Product Key]
    measures: [Product Count]
  Sales:
    columns: [Quantity, Net Price, Order Date]
    measures: [Sales Amount, Total Orders]

filters:                                              # report-level filters
  - Product.Color Categorical: Red, Blue (hidden)

pages:
  - name: Sales Overview  # active
    id: page1
    path: Report.Report/definition/pages/page1
    size: 1920 x 1080
    filters:                                          # page-level filters
      - Product.Category Categorical: Bikes
    visuals:
      - name: revenueChart
        type: clusteredColumnChart
        path: Report.Report/definition/pages/page1/visuals/a1b2c3
        position: 50, 100
        size: 600 x 400
        title: Revenue by Category
        bindings:
          Category: Product.Category
          Y: Sales.Sales Amount (measure)
        sort: Sales.Sales Amount (measure) Descending  # sort definition
        formatting: {legend: true (Top), labels: false} # key chart formatting
        conditionalFormatting:                           # conditional formatting
          - dataPoint.fill: #FF0000 @ 0 -> #FFFF00 @ 50 -> #00FF00 @ 100
        filters:                                        # visual-level filters
          - Sales.Sales Amount Advanced: >= 1000
```

### pbi validate

Check project files for structural errors. See [Validation](validation.md).

### pbi capabilities

Show a capability matrix for the current CLI surface: what is already covered, what is partial, and what is still missing for a fuller PBIR editor.

```bash
pbi capabilities
pbi capabilities --status blocked
pbi capabilities --json
```

### pbi report

Show or edit schema-backed report metadata in `definition/report.json`.

```bash
pbi report get
pbi report get layoutOptimization
pbi report set layoutOptimization=PhonePortrait
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom
pbi report props
```

## Detailed References

| Topic | File |
|-------|------|
| [Report Commands](report.md) | Report metadata and settings |
| [Page Commands](pages.md) | Create, configure, template, drillthrough, tooltip pages |
| [Visual Commands](visuals.md) | Create, style, move, group, sort, format visuals |
| [Properties Reference](properties.md) | All visual and container properties |
| [Data & Filters](data.md) | Data binding, filters, semantic model |
| [Interactions & Navigation](interactions.md) | Visual interactions, button actions |
| [Bookmarks](bookmarks.md) | Bookmark management |
| [Themes](themes.md) | Theme apply, export, remove |
| [Capabilities & Roadmap](capabilities.md) | Current coverage and next expansion areas |
| [Fixture Spec](fixtures.md) | PBIP/PBIR examples still needed to close feature gaps |
| [Implementation Roadmap](roadmap.md) | Schema-first expansion priorities |
| [Validation & Structure](validation.md) | Schema validation, PBIR file structure |
