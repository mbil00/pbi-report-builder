# Report Fixture Spec 02: Model-Heavy Semantic Fixture

## Purpose

This PBIP fixture is optimized for semantic model editing and validation rather than broad report surface area. It should stress model commands and YAML model round-trip features while still containing enough visuals to prove bindings survive changes.

Primary test targets:

- `pbi model table/column/measure/relationship/hierarchy`
- `pbi model export/apply/deps/check/search/path/fields`
- rename cascade behavior
- hide/unhide behavior
- format and metadata writes
- YAML model round-trip
- visual bindings after model edits

## Build Constraints

- PBIP project, imported local data only.
- Keep data compact and deterministic.
- Prioritize richer metadata and relationships over visual count.
- Avoid unsupported Power BI features that cannot survive PBIP source control export cleanly.

## Domain

Use a finance and operations planning domain with actuals, budgets, departments, accounts, scenarios, and dates.

## Data Model

### Tables

#### `GL_Actuals`

Grain: monthly actual amount by cost center and account.

Columns:

- `ActualKey` integer
- `Date` date
- `DepartmentKey` integer
- `CostCenterKey` integer
- `AccountKey` integer
- `ScenarioKey` integer
- `Amount` decimal
- `FTE` decimal
- `CommentCode` text

#### `Budget`

Grain: monthly budget amount by department and account.

Columns:

- `BudgetKey` integer
- `Date` date
- `DepartmentKey` integer
- `AccountKey` integer
- `ScenarioKey` integer
- `BudgetAmount` decimal
- `BudgetFTE` decimal

#### `Forecast`

Grain: monthly forecast amount by department and account.

Columns:

- `ForecastKey` integer
- `Date` date
- `DepartmentKey` integer
- `AccountKey` integer
- `ScenarioKey` integer
- `ForecastAmount` decimal

#### `Department`

Columns:

- `DepartmentKey` integer
- `DepartmentCode` text
- `DepartmentName` text
- `Division` text
- `VPName` text
- `IsCorporate` boolean

#### `CostCenter`

Columns:

- `CostCenterKey` integer
- `CostCenterCode` text
- `CostCenterName` text
- `DepartmentKey` integer
- `ManagerName` text

#### `Account`

Columns:

- `AccountKey` integer
- `AccountNumber` text
- `AccountName` text
- `AccountGroup` text
- `AccountSubgroup` text
- `AccountType` text
- `Sign` whole number
- `SortOrder` whole number

Requirements:

- `AccountName` sorted by `SortOrder`
- at least some hidden technical columns

#### `Scenario`

Columns:

- `ScenarioKey` integer
- `ScenarioName` text
- `ScenarioType` text

Use values such as `Actual`, `Budget`, `Forecast`.

#### `Date`

Columns:

- `Date` date
- `Year` whole number
- `Quarter` text
- `MonthNumber` whole number
- `MonthName` text
- `YearMonth` text
- `FiscalYear` text
- `FiscalQuarter` text
- `FiscalMonthNumber` whole number

Requirements:

- hierarchy `Fiscal Calendar`: `FiscalYear > FiscalQuarter > MonthName`
- `MonthName` sorted by `MonthNumber`

#### `ExchangeRate`

Columns:

- `Date` date
- `CurrencyCode` text
- `RateToUSD` decimal

Optional if you want one more relationship path and a few richer measures.

### Relationships

Required:

- facts to `Date`
- facts to `Department`
- facts to `Account`
- `CostCenter[DepartmentKey]` -> `Department[DepartmentKey]`
- facts to `Scenario`

Recommended:

- `GL_Actuals[CostCenterKey]` -> `CostCenter[CostCenterKey]`

Include a realistic but clean star-like model. One inactive relationship is useful if convenient.

## Metadata Requirements

This fixture should be rich in model metadata.

### Columns

Ensure multiple columns use:

- descriptions
- display folders
- `sortByColumn`
- `dataCategory` where appropriate
- explicit `summarizeBy`
- hidden columns

Suggested hidden columns:

- surrogate keys
- technical import keys
- some comment or code columns

### Measures

Use a dedicated `Measures` table if preferred.

Required display folders:

- `Actuals`
- `Budget`
- `Forecast`
- `Variance`
- `Ratios`
- `Time Intelligence`

Add descriptions to at least 10 measures.

## Measures

Required measures:

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

Dependency requirements:

- at least 5 measures referencing other measures
- at least 1 measure with nested dependencies 3 levels deep

## Calculated Columns

Include at least 3 calculated columns:

- `Department[Department Label] = Department[DepartmentCode] & " - " & Department[DepartmentName]`
- `Account[Account Label] = Account[AccountNumber] & " - " & Account[AccountName]`
- `Date[Month Start] = DATE ( YEAR ( 'Date'[Date] ), MONTH ( 'Date'[Date] ), 1 )`

## Calculated Table

Include one calculated table:

- `Variance Bands`

Suggested columns:

- `Band`
- `MinPct`
- `MaxPct`

Purpose: useful for tests around calculated table presence and searchability.

## Hierarchies

Required hierarchies:

- `Date[Fiscal Calendar]`
- `Department[Org]` with `Division > DepartmentName`
- `Account[P&L]` with `AccountGroup > AccountSubgroup > AccountName`

## Report Pages

Keep the report smaller than fixture 01, but include enough visuals to prove model bindings.

### 1. `Finance Overview`

Visuals:

- KPI cards: `Actual Amount`, `Budget Amount`, `Actual vs Budget`, `Actual vs Budget %`
- line and clustered column chart by `Date[YearMonth]`
- matrix by `Department[Division]` and `Department[DepartmentName]`
- slicers for `Scenario[ScenarioName]`, `Date[FiscalYear]`, `Account[AccountGroup]`

### 2. `Department Drill`

Visuals:

- bar chart by department
- table or matrix with account rows
- decomposition-friendly visual or tree map if available

Requirements:

- page should work as drillthrough target on department

### 3. `Account Detail`

Visuals:

- matrix using account hierarchy
- variance conditional formatting
- cards for expense actual and YoY

## Formatting and Interactions

Minimum requirements:

- at least one matrix with conditional formatting by measure
- at least one visual sorted by a measure
- at least one interaction override

## Validation-Oriented Requirements

This fixture should specifically support these edit scenarios:

- rename a measure and verify DAX cascades
- rename a column used in:
  - another column expression
  - a measure expression
  - a relationship
  - a hierarchy
- hide/unhide columns in bulk by pattern
- export and re-apply model YAML without losing metadata
- run dependency analysis on a nested measure
- run relationship checks without false positives on the clean baseline

## Acceptance Checklist

The exported PBIP should satisfy all of these:

- at least 8 model tables
- at least 3 hierarchies
- at least 15 measures
- at least 3 calculated columns
- at least 1 calculated table
- at least 5 hidden columns
- at least 5 measures in display folders
- at least 2 visuals bound to hierarchy-backed fields
- at least 1 drillthrough page
- at least 1 measure dependency chain of length 3 or more

## Export Notes to Capture

When this fixture is produced, also record:

- Power BI Desktop version used
- source data files used to build it
- any manual modeling steps that were required
- whether any feature was approximated because PBIP export did not preserve it cleanly

