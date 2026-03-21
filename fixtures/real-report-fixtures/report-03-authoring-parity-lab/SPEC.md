# Report 03: Authoring Parity Lab

## Purpose

This fixture is the first full acceptance report for the Phase 1-6 authoring expansion.

It is not just a sample report. It is a proof report:

- rich enough to exercise the CLI as a real report-building layer
- small enough to build and verify on one machine
- deterministic enough to keep as a tracked PBIP fixture

This report should be built primarily with `pbi` commands and YAML round-trips, then opened in Power BI Desktop only for final validation and save/export.

## Primary Goal

Demonstrate that the current app can build and maintain a real PBIP report with:

- builder-created visuals
- bookmarks and grouped state
- drillthrough, tooltip, and navigation wiring
- report-level metadata and resources
- theme-level style control and conditional formatting
- semantic-model perspectives, roles, partitions, and model annotations

## Base Data Model

Use the deterministic finance dataset and semantic model from:

- `fixtures/real-report-fixtures/report-02-model-heavy`

Do not invent a new model unless the existing one proves insufficient. The point is to reuse the richer model fixture that already contains:

- `Account`
- `Budget`
- `GL_Actuals`
- `Forecast`
- `Department`
- `CostCenter`
- `Scenario`
- `Date`
- `ExchangeRate`
- `Variance Bands`

Required existing model features to preserve and use:

- hierarchies:
  - `Account.P&L`
  - `Department.Org`
- sort-by-column behavior:
  - `Account.AccountName` sorted by `SortOrder`
- calculated table:
  - `Variance Bands`
- calculated columns already present in the model

## Model Authoring Additions

The report must explicitly exercise the new Phase 6 model-authoring surface.

### Model Annotations

Add at least these model annotations:

- `PBI_ProTooling = ["DevMode"]`
- `PBI_QueryOrder = [...]`
- `AuthoringParity = {"fixture":"report-03","phases":[1,2,3,4,5,6]}`

The third annotation is the proof annotation for this fixture and should be added via `pbi model annotation set`.

### Perspectives

Create these perspectives:

1. `Exec View`
   - include all:
     - `Department`
     - `Date`
   - include selected measures:
     - `Budget.Budget Amount`
     - `GL_Actuals.Actual Amount`
     - `Forecast.Forecast Amount`
   - include hierarchy:
     - `Department.Org`

2. `Finance View`
   - include all:
     - `Account`
     - `Department`
     - `Date`
     - `Scenario`
   - include measures:
     - `Budget.Budget Amount`
     - `GL_Actuals.Actual Amount`
     - `Forecast.Forecast Amount`

3. `Variance Analysis`
   - include all:
     - `Variance Bands`
   - include columns/measures needed for variance pages only

### Roles / RLS

Create these roles:

1. `Corporate Only`
   - permission: `read`
   - filter:
     - `Department`: `Department[Division] = "Corporate"`

2. `Finance Readers`
   - permission: `readRefresh`
   - filter:
     - `Department`: `Department[Division] IN {"Corporate","Shared Services"}`
   - at least one sample member:
     - `finance@example.com`

3. `Executive Demo`
   - permission: `read`
   - no members required
   - filter:
     - `Department`: `Department[IsCorporate] = TRUE()`

### Partitions

The report must preserve the existing import partitions and explicitly prove partition editing works.

Acceptance requirement:

- inspect at least one existing M partition via `pbi model partition get`
- update one non-critical partition source on a copied working branch or temp copy
- export/apply the partition through `model.yaml`

Suggested proof target:

- `Department.Department`

### Model Acceptance Evidence

The final exported `model.yaml` must contain:

- `model.annotations`
- `partitions`
- `roles`
- `perspectives`

## Report-Level Metadata

The report must exercise the Phase 4 surface.

### Report Annotations

Add:

- `README = "Authoring parity acceptance report"`
- `Owner = "pbi-report-builder"`
- `ProofLevel = "phase-1-6"`

### Resource Packages

Register at least two image resources:

1. `logo-finance`
   - used in page header
2. `watermark-grid`
   - used on one hidden or decorative page

### Data Source Variables

Add at least one report-level `dataSourceVariables` entry, even if it is only a placeholder for authoring proof.

Suggested example:

- `Environment = "Acceptance"`

### Optional Custom Visual Metadata

If a local org custom visual package is available, add one `organizationCustomVisuals` entry and place one visual.

If not available, keep this out of the mandatory acceptance bar.

## Theme

The report must use a custom theme authored through the app, not only Desktop formatting.

### Theme Direction

Style direction:

- executive finance dashboard
- calm light theme
- slate / ink / muted gold palette
- restrained but intentional contrast

Suggested base palette:

- background: `#F4F1EA`
- ink: `#1E2A36`
- slate: `#556270`
- accent gold: `#B38A3D`
- positive: `#3F7D5C`
- negative: `#A84C3D`

### Required Theme Features

1. Theme-level `visualStyles`
   - chart defaults
   - table/matrix defaults
   - card defaults
   - slicer defaults

2. Role-aware theme branch
   - at least one `visualStyles[visualType][role]` branch
   - suggested: chart `Series` role branch

3. Theme-level conditional formatting defaults
   - rules or gradient-based defaults used by at least one matrix or variance visual

4. Theme round-trip proof
   - `export` must include top-level `theme:`
   - `apply` must reapply it cleanly

## Pages

Use 7 pages total.

### 1. Executive Overview

Purpose:

- primary landing page
- strongest proof of builder-created visuals and layout helpers

Required visuals:

- 4 KPI cards in a stamped component row:
  - Actual
  - Budget
  - Forecast
  - Variance %
- 1 clustered column chart:
  - Axis: `Department.DepartmentName`
  - Values: `GL_Actuals.Actual Amount`
- 1 line and clustered column combo:
  - Axis: `Date.MonthName` or equivalent available month grain
  - Column values: Actual
  - Line values: Budget
- 1 donut or pie:
  - Group: `Account.AccountGroup`
  - Values: Actual
- 2 slicers:
  - `Department.Division`
  - `Scenario.ScenarioName`
- 1 image logo in header
- 1 text box with a short report narrative

Required interactions:

- division slicer filters all visuals
- donut filters the matrix on Page 2 but does not affect the KPI row
- one chart-to-chart interaction explicitly set to `none`

Required navigation:

- button to `Department Breakdown`
- button to bookmark group for view toggles
- button to external documentation URL

### 2. Department Breakdown

Purpose:

- matrix-heavy page proving formatting, drillthrough, bookmarks, and conditional formatting

Required visuals:

- matrix with:
  - rows: `Department.Org`
  - columns: `Scenario.ScenarioName`
  - values:
    - Actual
    - Budget
    - Forecast
    - Variance %
- clustered bar chart by `Department.DepartmentName`
- detail table with account-level rows
- slicer for `Account.AccountGroup`

Required formatting:

- conditional formatting on variance values
- at least one rules-based format
- at least one gradient format

Required bookmarks:

- `Show Matrix`
- `Show Chart`
- `Finance Only`

These should belong to a bookmark group named `Department Views`.

### 3. Account Drillthrough

Purpose:

- dedicated drillthrough target

Required page settings:

- drillthrough page
- bound to account-level context

Required visuals:

- account detail card
- monthly actual vs budget chart
- transaction-style detail table

Required navigation:

- `Back` button

### 4. Department Tooltip

Purpose:

- dedicated tooltip page

Required page settings:

- tooltip page

Required visuals:

- mini card for Actual
- mini card for Budget
- small variance bar
- optional small sparkline or line chart

This tooltip must be assigned to at least one visual on the Executive Overview page.

### 5. Variance Diagnostics

Purpose:

- prove table, matrix, conditional formatting, filters, and theme defaults together

Required visuals:

- table or matrix by `Account.P&L`
- scatter or bar visual showing major variance bands
- slicer for `Department.DepartmentName`
- textbox describing how variance is interpreted

Required bookmarks:

- one bookmark hiding diagnostics detail
- one bookmark showing diagnostics detail

### 6. Navigation Lab

Purpose:

- concentrated action proof page

Required elements:

- page navigation button
- bookmark navigation button
- drillthrough action button
- back button
- URL button
- tooltip-targeted visual

This page exists mainly to prove action wiring and make regressions obvious.

### 7. Build Notes

Purpose:

- hidden page
- authoring/QA only

Required elements:

- textbox listing:
  - fixture name
  - Desktop version
  - build date
  - generated via `pbi` workflows
- optional watermark image

The page must be hidden.

## Components, Templates, And Reuse

The report should explicitly prove higher-level authoring helpers.

### Required Component Proofs

1. `kpi_tile`
   - reusable KPI card container
   - stamped 4 times on Executive Overview

2. `page_header`
   - image + title + subtitle pattern
   - reused on at least 3 pages

### Optional Template Proof

If practical, create one page from a saved template rather than hand-building every page from scratch.

## Visual Builder Coverage

The report must use builder-created or builder-updated visuals from these families:

- card
- clustered column or bar
- line or combo
- donut or pie
- slicer
- table
- matrix

At least one builder-created visual must rely on model-aware sort inference.

Suggested proof:

- account labels or month/category sort driven by model metadata

## Bookmark And Navigation Proof

The final PBIP must contain:

- at least 6 bookmarks
- at least 2 bookmark groups
- visibility state changes
- filter state changes
- sort/projection or object state changes where available

Navigation coverage must include:

- `nav page set`
- `nav bookmark set`
- `nav back set`
- `nav url set`
- `nav drillthrough set`
- `nav tooltip set`

## YAML Round-Trip Proof

The report is only accepted if this workflow succeeds on a copy:

1. `pbi export report-03.yaml`
2. `pbi diff report-03.yaml`
3. `pbi apply report-03.yaml --dry-run`
4. `pbi apply report-03.yaml`
5. `pbi model export -o model.yaml`
6. `pbi model apply model.yaml --dry-run`
7. `pbi model apply model.yaml`

Required exported sections:

- `report:`
- `theme:`
- `bookmarks:`
- `pages:`
- model YAML containing:
  - `model`
  - `partitions`
  - `roles`
  - `perspectives`

## Acceptance Matrix

Use this as the proof checklist.

| Area | Required evidence |
|------|-------------------|
| Visual builders | Builder-created chart, combo, card, slicer, table, matrix, donut/pie survive validate/export/apply |
| Bookmark/state | Bookmark groups plus richer state summaries are visible in `bookmark list/get` |
| Navigation | Page, bookmark, back, URL, drillthrough, and tooltip actions all exist in the PBIP |
| Report metadata | report annotations, resource packages, data-source variables round-trip |
| Theme parity | nested `visualStyles`, role branch, and theme-level formatting defaults round-trip |
| Perspectives | `model perspective list/get` shows all 3 perspectives |
| Roles / RLS | `model role list/get`, `model role member list`, `model role filter list` all show expected data |
| Partitions | `model partition list/get` and YAML round-trip preserve source and mode |
| Model annotations | `model annotation list/get` shows proof annotations |
| Images/resources | header logo is present and registered |
| Components | KPI strip is stamped from a component rather than hand-copied |
| Hidden/tooltip/drillthrough pages | all page types exist and are wired |

## Build Guidance

Recommended build order:

1. start from a copy of `report-02-model-heavy`
2. add the custom theme and report annotations
3. add model perspectives, roles, partitions proof edits, and model annotations
4. build the `Executive Overview` page with builder-created visuals
5. build `Department Breakdown`, `Account Drillthrough`, and `Department Tooltip`
6. wire bookmarks and navigation
7. add the `Navigation Lab` and hidden `Build Notes` page
8. export as PBIP and run the acceptance workflow above

## Deliverable

The final tracked fixture should live at:

- `fixtures/real-report-fixtures/report-03-authoring-parity-lab/`

and should include:

- exported PBIP project
- any deterministic local assets used by the report
- this spec
- a short build note with the Power BI Desktop version used
