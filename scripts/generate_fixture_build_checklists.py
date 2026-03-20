#!/usr/bin/env python3
"""Generate build checklists for the real-report fixture datasets.

Usage:
    python scripts/generate_fixture_build_checklists.py
    python scripts/generate_fixture_build_checklists.py --output fixtures/real-report-fixtures
"""

from __future__ import annotations

import argparse
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "fixtures" / "real-report-fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Base output directory containing generated fixture datasets.",
    )
    args = parser.parse_args()

    output_root = args.output.resolve()
    if not output_root.exists():
        raise SystemExit(f"Output directory does not exist: {output_root}")

    kitchen_root = output_root / "report-01-kitchen-sink"
    model_root = output_root / "report-02-model-heavy"
    kitchen_dir = kitchen_root / "data"
    model_dir = model_root / "data"

    if not kitchen_root.exists():
        raise SystemExit(f"Missing fixture directory: {kitchen_root}")
    if not model_root.exists():
        raise SystemExit(f"Missing fixture directory: {model_root}")
    if not kitchen_dir.exists():
        raise SystemExit(f"Missing dataset directory: {kitchen_dir}")
    if not model_dir.exists():
        raise SystemExit(f"Missing dataset directory: {model_dir}")

    (kitchen_root / "BUILD-CHECKLIST.md").write_text(
        build_kitchen_sink_checklist(kitchen_dir),
        encoding="utf-8",
    )
    (model_root / "BUILD-CHECKLIST.md").write_text(
        build_model_heavy_checklist(model_dir),
        encoding="utf-8",
    )

    print(f"Wrote build checklists to {output_root}")
    print(f"  {kitchen_root / 'BUILD-CHECKLIST.md'}")
    print(f"  {model_root / 'BUILD-CHECKLIST.md'}")


def build_kitchen_sink_checklist(dataset_dir: Path) -> str:
    files = sorted(path.name for path in dataset_dir.glob("*.csv"))
    return f"""# Build Checklist: Report 01 Kitchen Sink

## Goal

Create a PBIP report fixture that exercises the widest practical report-authoring surface of `pbi-report-builder`.

Dataset location:

- `{dataset_dir}`

CSV files to import:

{bullet_list(files)}

## 1. Create The Base PBIP Project

1. Open Power BI Desktop.
2. Create a new PBIP project named something like `KitchenSinkFixture`.
3. Save it as PBIP immediately so the model/report artifacts exist from the start.
4. Record the exact Power BI Desktop version used.

## 2. Load Data

Import these CSVs from `{dataset_dir}`:

- `Date.csv`
- `Product.csv`
- `Customer.csv`
- `Store.csv`
- `Channel.csv`
- `Promotion.csv`
- `Sales.csv`
- `Targets.csv`

Requirements:

- Use Import mode only.
- Keep table names exactly as listed above.
- Confirm data types after load instead of relying entirely on auto-detection.

## 3. Validate Column Types

Ensure these types are correct:

- Date columns as `Date`
- keys as whole numbers
- prices, cost, sales, margin, targets as decimal numbers
- boolean flags as true/false
- text attributes as text

Important columns:

- `Sales[OrderDate]`, `Sales[ShipDate]`
- `Date[Date]`
- `Product[LaunchDate]`
- `Customer[SignupDate]`
- `Store[OpenDate]`
- `Promotion[StartDate]`, `Promotion[EndDate]`

## 4. Create Relationships

Create these relationships:

- `Sales[OrderDate]` -> `Date[Date]` active
- `Sales[ShipDate]` -> `Date[Date]` inactive
- `Sales[ProductKey]` -> `Product[ProductKey]`
- `Sales[CustomerKey]` -> `Customer[CustomerKey]`
- `Sales[StoreKey]` -> `Store[StoreKey]`
- `Sales[ChannelKey]` -> `Channel[ChannelKey]`
- `Sales[PromotionKey]` -> `Promotion[PromotionKey]`
- `Targets[ChannelKey]` -> `Channel[ChannelKey]`

Preferred:

- if practical, relate `Targets[YearMonth]` to `Date[YearMonth]`

## 5. Model Cleanup

1. Mark `Date` as a date table using `Date[Date]`.
2. Sort `Date[MonthName]` by `Date[MonthNumber]`.
3. Create hierarchy `Date[Calendar]`:
   - `Year`
   - `Quarter`
   - `MonthName`
   - `Date`
4. Hide surrogate keys where appropriate:
   - `SalesKey`
   - foreign key columns
   - dimension key columns

## 6. Create Measures

Create these measures, ideally in a dedicated `Measures` table:

- `Revenue = SUM ( Sales[SalesAmount] )`
- `Cost = SUMX ( Sales, Sales[Quantity] * Sales[UnitCost] )`
- `Margin = [Revenue] - [Cost]`
- `Margin % = DIVIDE ( [Margin], [Revenue] )`
- `Orders = DISTINCTCOUNT ( Sales[OrderNumber] )`
- `Units = SUM ( Sales[Quantity] )`
- `Avg Order Value = DIVIDE ( [Revenue], [Orders] )`
- `Return Rate = DIVIDE ( CALCULATE ( [Orders], Sales[ReturnedFlag] = TRUE() ), [Orders] )`
- `Revenue Target = SUM ( Targets[SalesTarget] )`
- `Target Variance = [Revenue] - [Revenue Target]`
- `Revenue YTD = TOTALYTD ( [Revenue], 'Date'[Date] )`
- `Revenue YoY = [Revenue] - CALCULATE ( [Revenue], DATEADD ( 'Date'[Date], -1, YEAR ) )`
- `Revenue YoY % = DIVIDE ( [Revenue YoY], CALCULATE ( [Revenue], DATEADD ( 'Date'[Date], -1, YEAR ) ) )`
- `Revenue by Ship Date = CALCULATE ( [Revenue], USERELATIONSHIP ( Sales[ShipDate], 'Date'[Date] ) )`

Metadata:

- add descriptions to at least 5 measures
- use display folders:
  - `Sales`
  - `Profitability`
  - `Targets`
  - `Time Intelligence`

## 7. Apply Report Metadata Settings

Change report settings so they are explicit and testable:

- pages position set to `Bottom`
- enhanced tooltips enabled
- cross-report drillthrough enabled
- inline exploration explicitly set
- layout optimization explicitly set

## 8. Create And Apply A Custom Theme

1. Create a custom theme JSON and apply it.
2. Include:
   - non-default foreground/background/accent
   - at least 6 `dataColors`
   - text class overrides
3. Keep the theme file with the PBIP project so the registered resource is exported.

Also intentionally create:

- at least 3 redundant per-visual overrides matching the theme
- at least 3 conflicting per-visual overrides differing from the theme

This is required for `theme audit` and `theme migrate` testing.

## 9. Register Images

Add at least these images:

- `logo.png`
- `product-hero.png`
- one extra image that remains unreferenced

Requirements:

- at least two images must be registered resources
- one image must remain unused so `image prune` has work to do

## 10. Build Pages

Create these pages with the exact names shown.

### `Executive Overview`

Include:

- hero text box
- image visual with company logo
- 4 KPI cards
- clustered column chart by month
- line or combo chart with target comparison
- donut chart by channel
- slicers for year, category, region
- navigation buttons:
  - to `Product Detail`
  - to `Regional Detail`
  - to a bookmark state

Additional requirements:

- include a visual group with multiple child visuals
- include at least one custom visual title
- include at least one hidden visual

### `Product Detail`

Include:

- matrix with category > subcategory > product
- bar chart for top 10 products
- scatter chart for revenue vs margin percent
- product detail cards
- image visual

Additional requirements:

- page must be a drillthrough target for `Product[Category]` and `Product[ProductName]`
- include matrix conditional formatting
- include a top N visual-level filter

### `Regional Detail`

Include:

- stacked bar by region and channel
- store table
- slicer for store type
- back button

Additional requirements:

- add at least one interaction override, not just defaults

### `Tooltip - Order Context`

Requirements:

- set page type to tooltip
- use small tooltip canvas
- include KPI-style visuals for hovered context

### `Hidden QA Page`

Requirements:

- hide the page in view mode
- include at least one textbox and one chart

## 11. Configure Filters

Make sure these exist somewhere in the report:

- report-level categorical filter
- page-level filter
- visual-level filter
- include filter
- exclude filter
- range filter
- top N filter
- advanced text filter using `contains`

## 12. Configure Bookmarks

Create at least:

- `Default View`
- `Focus On Online`
- `Hide Slicers`

Requirements:

- at least one bookmark changes display state
- at least one bookmark preserves some non-display state

## 13. Configure Navigation

Include buttons for:

- page navigation
- bookmark navigation
- URL navigation
- back navigation

## 14. Final Verification Before Commit

Confirm all of the following:

- custom theme exported as registered resource
- at least 5 pages, including 1 hidden and 1 tooltip page
- at least 15 visuals total
- at least 1 visual group
- at least 2 bookmarks
- at least 2 action buttons
- at least 2 registered images, with 1 unreferenced
- at least 1 matrix and 1 table
- at least 1 drillthrough target
- at least 1 tooltip page binding

## 15. Export Hygiene

Before handing off the fixture:

1. Save and close the PBIP project.
2. Reopen it and confirm it still renders cleanly.
3. Commit the PBIP exactly as exported.
4. Record:
   - Desktop version
   - any manual deviations from the spec
   - any Power BI feature that exported differently than expected
"""


def build_model_heavy_checklist(dataset_dir: Path) -> str:
    files = sorted(path.name for path in dataset_dir.glob("*.csv"))
    return f"""# Build Checklist: Report 02 Model Heavy

## Goal

Create a PBIP fixture optimized for semantic model editing, dependency analysis, metadata preservation, and model YAML round-trip testing.

Dataset location:

- `{dataset_dir}`

CSV files to import:

{bullet_list(files)}

## 1. Create The Base PBIP Project

1. Open Power BI Desktop.
2. Create a new PBIP project named something like `ModelHeavyFixture`.
3. Save it immediately as PBIP.
4. Record the exact Desktop version used.

## 2. Load Data

Import these CSVs from `{dataset_dir}`:

- `Date.csv`
- `Department.csv`
- `CostCenter.csv`
- `Account.csv`
- `Scenario.csv`
- `GL_Actuals.csv`
- `Budget.csv`
- `Forecast.csv`
- `ExchangeRate.csv`

Use Import mode only.

## 3. Validate Column Types

Ensure these types are correct:

- date columns as `Date`
- keys as whole numbers
- amount/fte/rate columns as decimal numbers
- `IsCorporate` as boolean
- names and codes as text

## 4. Create Relationships

Create these relationships:

- `GL_Actuals[Date]` -> `Date[Date]`
- `Budget[Date]` -> `Date[Date]`
- `Forecast[Date]` -> `Date[Date]`
- `GL_Actuals[DepartmentKey]` -> `Department[DepartmentKey]`
- `Budget[DepartmentKey]` -> `Department[DepartmentKey]`
- `Forecast[DepartmentKey]` -> `Department[DepartmentKey]`
- `GL_Actuals[AccountKey]` -> `Account[AccountKey]`
- `Budget[AccountKey]` -> `Account[AccountKey]`
- `Forecast[AccountKey]` -> `Account[AccountKey]`
- `GL_Actuals[ScenarioKey]` -> `Scenario[ScenarioKey]`
- `Budget[ScenarioKey]` -> `Scenario[ScenarioKey]`
- `Forecast[ScenarioKey]` -> `Scenario[ScenarioKey]`
- `CostCenter[DepartmentKey]` -> `Department[DepartmentKey]`
- `GL_Actuals[CostCenterKey]` -> `CostCenter[CostCenterKey]`

Optional:

- add one inactive relationship if you want one extra validation/use-case surface

## 5. Model Cleanup

1. Mark `Date` as a date table using `Date[Date]`.
2. Sort `Date[MonthName]` by `Date[MonthNumber]`.
3. Sort `Account[AccountName]` by `Account[SortOrder]`.
4. Hide technical columns:
   - surrogate keys
   - scenario keys
   - comment codes if not needed in visuals
   - any helper sort columns that should not be user-facing

Minimum hidden columns: 5.

## 6. Create Hierarchies

Create these hierarchies:

- `Date[Fiscal Calendar]`:
  - `FiscalYear`
  - `FiscalQuarter`
  - `MonthName`
- `Department[Org]`:
  - `Division`
  - `DepartmentName`
- `Account[P&L]`:
  - `AccountGroup`
  - `AccountSubgroup`
  - `AccountName`

## 7. Create Calculated Columns

Create at least:

- `Department Label = Department[DepartmentCode] & " - " & Department[DepartmentName]`
- `Account Label = Account[AccountNumber] & " - " & Account[AccountName]`
- `Month Start = DATE ( YEAR ( 'Date'[Date] ), MONTH ( 'Date'[Date] ), 1 )`

## 8. Create Calculated Table

Create calculated table:

- `Variance Bands`

Suggested structure:

- `Band`
- `MinPct`
- `MaxPct`

Use simple `DATATABLE` or another deterministic DAX form.

## 9. Create Measures

Create these measures, ideally in a dedicated `Measures` table:

- `Actual Amount = SUM ( GL_Actuals[Amount] )`
- `Budget Amount = SUM ( Budget[BudgetAmount] )`
- `Forecast Amount = SUM ( Forecast[ForecastAmount] )`
- `Actual vs Budget = [Actual Amount] - [Budget Amount]`
- `Actual vs Budget % = DIVIDE ( [Actual vs Budget], [Budget Amount] )`
- `Actual vs Forecast = [Actual Amount] - [Forecast Amount]`
- `FTE Actual = SUM ( GL_Actuals[FTE] )`
- `FTE Budget = SUM ( Budget[BudgetFTE] )`
- `Average Actual per FTE = DIVIDE ( [Actual Amount], [FTE Actual] )`
- `YTD Actual = TOTALYTD ( [Actual Amount], 'Date'[Date] )`
- `Prior Year Actual = CALCULATE ( [Actual Amount], DATEADD ( 'Date'[Date], -1, YEAR ) )`
- `Actual YoY = [Actual Amount] - [Prior Year Actual]`
- `Actual YoY % = DIVIDE ( [Actual YoY], [Prior Year Actual] )`
- `Corporate Actual = CALCULATE ( [Actual Amount], Department[IsCorporate] = TRUE() )`
- `Expense Actual = CALCULATE ( [Actual Amount], Account[AccountType] = "Expense" )`

Requirements:

- at least 15 measures total
- at least 5 measures referencing other measures
- at least one dependency chain 3 levels deep

## 10. Add Measure Metadata

Use display folders:

- `Actuals`
- `Budget`
- `Forecast`
- `Variance`
- `Ratios`
- `Time Intelligence`

Also:

- add descriptions to at least 10 measures
- add descriptions to several visible columns
- add display folders to some columns where appropriate

## 11. Build Report Pages

Create these pages with the exact names shown.

### `Finance Overview`

Include:

- KPI cards for actual, budget, variance, variance percent
- line and clustered column chart by `Date[YearMonth]`
- matrix by department
- slicers for scenario, fiscal year, account group

### `Department Drill`

Include:

- department bar chart
- account table or matrix
- one additional explanatory visual

Requirements:

- page acts as drillthrough target on department

### `Account Detail`

Include:

- matrix using account hierarchy
- conditional formatting on variance
- cards for expense and YoY metrics

## 12. Add Sorting And Formatting

Make sure the report includes:

- at least one matrix with conditional formatting by measure
- at least one visual sorted by a measure
- at least one interaction override

## 13. Validation-Focused Scenarios To Preserve

Before finalizing, confirm the model supports these future tests:

- rename a measure and cascade DAX references
- rename a column used in:
  - another column expression
  - a measure expression
  - a relationship
  - a hierarchy
- hide/unhide columns by regex or naming pattern
- model export/apply round-trip without metadata loss
- dependency analysis on nested measures
- relationship validation with a clean baseline

## 14. Final Verification Before Commit

Confirm all of the following:

- at least 8 model tables
- at least 3 hierarchies
- at least 15 measures
- at least 3 calculated columns
- at least 1 calculated table
- at least 5 hidden columns
- hierarchy-backed visuals exist
- at least 1 drillthrough page exists
- nested measure dependency chain of length 3 or more exists

## 15. Export Hygiene

Before handing off the fixture:

1. Save and close the PBIP project.
2. Reopen it to verify model and visuals still load correctly.
3. Commit the PBIP exactly as exported.
4. Record:
   - Desktop version
   - any deviations from the spec
   - any manual steps that were unexpectedly required
"""


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items)


if __name__ == "__main__":
    main()
