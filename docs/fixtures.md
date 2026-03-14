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

- [ ] Passthrough filter fixture

### Useful Next

- [ ] Native Power BI Include / Exclude examples
- [ ] Native Power BI Tuple examples
- [ ] Missing advanced filter variants
- [ ] Actual field parameter examples
- [ ] Any slicer behaviors not already covered by the sample report

### Covered Enough For Now

- [x] Top N filter shape
  Source: `/tmp/pbip-demo/src/Report04.Report/definition/pages/708d7c04691a88810062/visuals/624d1cd33dddc2386da0/visual.json`
  Notes: this sample was used to implement the schema-backed `TopN` writer.
- [x] Relative Date filter shapes
  Source: `fixtures/sample-report/SampleReport.Report/definition/report.json`
  Notes: report/page/visual examples now cover `InNext`, `InLast`, and `InThis` exported shapes.
- [x] Relative Time filter shapes
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/80e0ecafc8e0e031e091/visuals/d8e7ea99dd81e99a0b03/visual.json`
  Notes: this sample covers the exported `InLast` and `InNext` relative-time `Between` patterns.
- [x] Visual Top N fixtures
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/a03dd607c2d7b5054706`
  Notes: the sample page named `04 VisualTopN` still exports ordinary `TopN` filters; no separate `VisualTopN` payload has been observed.
- [x] Bookmark state examples
  Source: `fixtures/sample-report/SampleReport.Report/definition/bookmarks`
  Notes: the sample includes bookmarks for filters, sort state, visibility changes, and a bookmark navigator.
- [x] Navigation and action examples
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/8cc5b2c8090b5e0e1415`
  Notes: the sample includes page navigation, bookmark, drillthrough, and web URL buttons.
- [x] Drillthrough and tooltip examples
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/b868b2039b03c0990728` and `fixtures/sample-report/SampleReport.Report/definition/pages/b62a600c2e9a0e7a01d6`
  Notes: the sample includes a drillthrough page plus a hidden tooltip page with a back button.
- [x] Core slicer behavior examples
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/8b17add4693ee01b15d7`
  Notes: the sample includes hierarchy slicers, synced slicers, and multiple slicer configurations.
- [x] Bound visual role examples for newer built-in visuals
  Source: `fixtures/sample-report/SampleReport.Report/definition/pages/077330abc24a5c4069ee`
  Notes: this page now captures real binding shapes for `advancedSlicerVisual`, `listSlicer`, `textSlicer`, `barChart`, `columnChart`, `azureMap`, `decompositionTreeVisual`, `keyDriversVisual`, and `cardVisual`.

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

Status: `covered`

Create examples for a plain date column, not a datetime field.

- [x] Report-level relative date filter
- [x] Page-level relative date filter
- [x] Visual-level relative date filter
- [x] `InLast` example
- [x] `InThis` example
- [x] `InNext` example
- [x] `Days` unit example
- [x] `Months` unit example
- [x] include-today `on`
- [x] include-today `off`

Preferred field:

- `Date[Date]`

### 2. Relative Time

Status: `covered`

Create examples for a real datetime column.

- [x] Visual-level relative time filter
- [x] last 15 minutes
- [x] last 1 hour
- [x] next 1 hour

Preferred field:

- `Date[DateTime]`

### 3. Visual Top N

Status: `covered`

The current sample report page named `04 VisualTopN` exports plain `TopN` filters rather than a distinct `VisualTopN` payload.

- [x] Visual-level `Top` example
- [x] Visual-level `Bottom` example
- [x] target field is a category column
- [x] order-by field is a measure
- [x] cross-table order-by example

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

Status: `partial`

- [x] `is`
- [x] `is not`
- [x] `contains`
- [x] `does not contain`
- [x] `starts with`
- [ ] `ends with`
- [x] `is blank`
- [x] `is not blank`

Source:

- `fixtures/sample-report/SampleReport.Report/definition/pages/2de7f287b823385150d1/visuals/256b4535129be547c9b6/visual.json`

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

Status: `covered`

- [x] bookmark that captures filters
- [x] bookmark that captures sort state
- [x] bookmark that changes visibility
- [x] bookmark navigator

### 10. Buttons and Navigation

Status: `covered`

- [x] page navigation button
- [x] bookmark button
- [x] back button
- [x] drillthrough button
- [x] web URL button

### 11. Drillthrough and Tooltip

Status: `covered`

- [x] drillthrough target page with passed fields
- [x] tooltip page bound to a visual

### 12. Field Parameters

Status: `needed`

- [ ] axis switch parameter
- [ ] measure switch parameter

Notes:

- The sample report includes a page named `10 Field Parameters`, but no field-parameter table or parameter-driven visual was found in the exported semantic model/report definition.

### 13. Slicers

Status: `partial`

- [x] hierarchy slicer
- [ ] relative date slicer
- [ ] between slicer
- [ ] dropdown slicer with search
- [x] synced slicers across pages

## Notes To Capture With Each Fixture

For each report or page you add, include a short note in the commit message or PR description covering:

- which page contains which scenario
- which field was filtered
- which scope was used: report, page, or visual
- the exact Power BI UI path used if it was non-obvious
- whether the exported shape matched expectations or was surprising
