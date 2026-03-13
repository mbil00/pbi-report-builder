# PBIR Fixture Spec

This document tracks the example PBIP/PBIR fixtures needed to close the remaining gap between Power BI authoring and this CLI.

Use this as the source of truth for sample reports to build or collect.

The repository also includes a purpose-built CSV bundle for creating these fixtures in [fixtures/sample-data/README.md](/home/mbil/Projects/pbi-report-builder/fixtures/sample-data/README.md).

## Delivery Rules

Every fixture should be committed as a real exported `PBIP` project:

- keep the `.pbip`
- keep the full `.Report/definition/...` tree
- keep the `.SemanticModel/...` tree
- do not hand-edit the exported JSON after saving from Power BI Desktop
- use clear page names and, when practical, clear visual names
- prefer small purpose-built reports over large mixed examples

## Status Legend

- `needed`: required to implement or validate a missing writer
- `useful`: not blocking right now, but valuable for parity checks or future work
- `covered`: already represented well enough by current fixtures or implementation

## Current Priority

### Needed Now

- [ ] Relative Date filter fixtures
- [ ] Relative Time filter fixtures
- [ ] Visual Top N fixtures
- [ ] Passthrough filter fixture

### Useful Next

- [ ] Native Power BI Include / Exclude examples
- [ ] Native Power BI Tuple examples
- [ ] Richer Advanced filter examples
- [ ] Bookmark state examples
- [ ] Navigation / action examples
- [ ] Drillthrough / tooltip examples
- [ ] Field parameter examples
- [ ] Slicer behavior examples

### Covered Enough For Now

- [x] Top N filter shape
  Source: `/tmp/pbip-demo/src/Report04.Report/definition/pages/708d7c04691a88810062/visuals/624d1cd33dddc2386da0/visual.json`
  Notes: this sample was used to implement the schema-backed `TopN` writer.

## Recommended Fixture Report Layout

If you build one consolidated sample project, use these page names:

- `01 Relative Date`
- `02 Relative Time`
- `03 TopN`
- `04 VisualTopN`
- `05 Passthrough`
- `06 Advanced Filters`
- `07 Bookmarks`
- `08 Navigation`
- `09 Drillthrough Tooltip`
- `10 Field Parameters`
- `11 Slicers`

Separate small PBIP projects are also fine if that is easier to build.

## Recommended Model

Use a tiny model with predictable names where possible:

- `Date[Date]`
- `Date[DateTime]`
- `Customers[Region]`
- `Customers[Segment]`
- `Product[Category]`
- `Product[Color]`
- `Product[Size]`
- `Sales[Revenue]`
- `Sales[Quantity]`
- `Sales[Order Count]` as a measure

This is not mandatory, but it makes fixture comparisons and CLI tests much simpler.

## Required Fixtures

### 1. Relative Date

Status: `needed`

Create examples for a plain date column, not a datetime field.

- [ ] Report-level relative date filter
- [ ] Page-level relative date filter
- [ ] Visual-level relative date filter
- [ ] `InLast` example
- [ ] `InThis` example
- [ ] `InNext` example
- [ ] `Days` unit example
- [ ] `Months` unit example
- [ ] include-today `on`
- [ ] include-today `off`

Preferred field:

- `Date[Date]`

### 2. Relative Time

Status: `needed`

Create examples for a real datetime column.

- [ ] Visual-level relative time filter
- [ ] last 15 minutes
- [ ] last 1 hour
- [ ] next 1 hour

Preferred field:

- `Date[DateTime]`

### 3. Visual Top N

Status: `needed`

This is distinct from the currently implemented `TopN` writer. We need examples that export as `VisualTopN`, if Power BI emits that type separately.

- [ ] Visual-level `Top` example
- [ ] Visual-level `Bottom` example
- [ ] target field is a category column
- [ ] order-by field is a measure
- [ ] cross-table order-by example

Preferred fields:

- target: `Customers[Region]` or `Product[Category]`
- order-by: `Sales[Revenue]` or `Sales[Order Count]`

### 4. Passthrough

Status: `needed`

Any real exported PBIR example that contains `type: "Passthrough"` is useful.

- [ ] At least one exported Passthrough example
- [ ] Record the Power BI workflow that created it

## Useful Parity Fixtures

### 5. Native Include / Exclude

Status: `useful`

We already support these, but exported Power BI examples help verify parity.

- [ ] Include filter created in Power BI
- [ ] Exclude filter created in Power BI
- [ ] report/page/visual scope if practical

### 6. Native Tuple

Status: `useful`

- [ ] Same-table multi-column tuple
- [ ] cross-table tuple if Power BI can emit one

### 7. Richer Advanced Filters

Status: `useful`

- [ ] `is`
- [ ] `is not`
- [ ] `contains`
- [ ] `does not contain`
- [ ] `starts with`
- [ ] `ends with`
- [ ] `is blank`
- [ ] `is not blank`

### 8. Top N Variants

Status: `useful`

The basic Top N shape is already covered, but more scope variants help prove whether Power BI exports different object structures by level.

- [ ] report-level Top N
- [ ] page-level Top N
- [ ] visual-level Top N
- [ ] same-table order field
- [ ] cross-table order field

## Useful Non-Filter Fixtures

### 9. Bookmark State

Status: `useful`

- [ ] bookmark that captures filters
- [ ] bookmark that captures sort state
- [ ] bookmark that changes visibility
- [ ] bookmark navigator

### 10. Buttons and Navigation

Status: `useful`

- [ ] page navigation button
- [ ] bookmark button
- [ ] back button
- [ ] drillthrough button
- [ ] web URL button

### 11. Drillthrough and Tooltip

Status: `useful`

- [ ] drillthrough target page with passed fields
- [ ] tooltip page bound to a visual

### 12. Field Parameters

Status: `useful`

- [ ] axis switch parameter
- [ ] measure switch parameter

### 13. Slicers

Status: `useful`

- [ ] hierarchy slicer
- [ ] relative date slicer
- [ ] between slicer
- [ ] dropdown slicer with search
- [ ] synced slicers across pages

## Notes To Capture With Each Fixture

For each report or page you add, include a short note in the commit message or PR description covering:

- which page contains which scenario
- which field was filtered
- which scope was used: report, page, or visual
- the exact Power BI UI path used if it was non-obvious
- whether the exported shape matched expectations or was surprising
