# Build Checklist: Report 02 Model Heavy

## Goal

Create a PBIP fixture optimized for semantic model editing, dependency analysis, metadata preservation, and model YAML round-trip testing.

Dataset location:

- `/home/mbil/Projects/pbi-report-builder/fixtures/real-report-fixtures/report-02-model-heavy/data`

CSV files to import:

- `Account.csv`
- `Budget.csv`
- `CostCenter.csv`
- `Date.csv`
- `Department.csv`
- `ExchangeRate.csv`
- `Forecast.csv`
- `GL_Actuals.csv`
- `Scenario.csv`

## 1. Create The Base PBIP Project

1. Open Power BI Desktop.
2. Create a new PBIP project named something like `ModelHeavyFixture`.
3. Save it immediately as PBIP.
4. Record the exact Desktop version used.

## 2. Load Data

Import these CSVs from `/home/mbil/Projects/pbi-report-builder/fixtures/real-report-fixtures/report-02-model-heavy/data`:

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
