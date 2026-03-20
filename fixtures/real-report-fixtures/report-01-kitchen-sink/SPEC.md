# Report Fixture Spec 01: Kitchen Sink Authoring Fixture

## Purpose

This PBIP fixture is the primary end-to-end report authoring test asset. It should exercise the widest practical surface area of the CLI against a realistic but compact report.

Primary test targets:

- `pbi map`
- `pbi report get/set`
- `pbi page export/import`
- `pbi visual get/set/set-all/create/copy/delete`
- `pbi filter`
- `pbi nav`
- `pbi bookmark`
- `pbi interaction`
- `pbi theme apply/export/audit/migrate`
- `pbi image create/list/prune`
- `pbi component create/apply/clone/delete`
- YAML `export` / `apply` / `diff`

## Build Constraints

- PBIP project, committed exactly as exported from Power BI Desktop.
- Import-mode model only. No DirectQuery, live connection, or external service dependency.
- Backing data should be local CSV or Enter Data tables stored with the fixture setup process.
- Keep file size moderate. Prefer 200-2,000 rows per table, not large fact volumes.
- Use stable local data values so output is deterministic.
- Include at least one custom theme and at least one registered image resource.

## Domain

Use a compact retail sales domain with dates, products, customers, stores, channels, promotions, and a few operational targets.

## Data Model

### Tables

#### `Sales`

Grain: one order line.

Columns:

- `SalesKey` integer, unique row key
- `OrderDate` date
- `ShipDate` date
- `CustomerKey` integer
- `ProductKey` integer
- `StoreKey` integer
- `ChannelKey` integer
- `PromotionKey` integer, nullable
- `OrderNumber` text
- `Quantity` whole number
- `UnitPrice` decimal
- `UnitCost` decimal
- `DiscountAmount` decimal
- `SalesAmount` decimal
- `MarginAmount` decimal
- `ReturnedFlag` boolean

Suggested rows: 1,000 to 3,000.

#### `Date`

Columns:

- `Date` date, unique
- `Year` whole number
- `Quarter` text
- `MonthNumber` whole number
- `MonthName` text
- `MonthShort` text
- `YearMonth` text
- `WeekOfYear` whole number
- `DayOfWeek` text
- `IsWeekend` boolean

Requirements:

- `MonthName` sorted by `MonthNumber`
- create hierarchy `Calendar`: `Year > Quarter > MonthName > Date`

#### `Product`

Columns:

- `ProductKey` integer
- `SKU` text
- `ProductName` text
- `Brand` text
- `Category` text
- `Subcategory` text
- `Color` text
- `UnitListPrice` decimal
- `LaunchDate` date
- `IsActive` boolean

#### `Customer`

Columns:

- `CustomerKey` integer
- `CustomerName` text
- `Segment` text
- `Region` text
- `Country` text
- `City` text
- `PostalCode` text
- `SignupDate` date

#### `Store`

Columns:

- `StoreKey` integer
- `StoreName` text
- `StoreType` text
- `Region` text
- `Manager` text
- `OpenDate` date

#### `Channel`

Columns:

- `ChannelKey` integer
- `ChannelName` text

Use values such as `Retail`, `Online`, `Distributor`.

#### `Promotion`

Columns:

- `PromotionKey` integer
- `PromotionName` text
- `PromotionType` text
- `StartDate` date
- `EndDate` date

#### `Targets`

Grain: monthly target by channel.

Columns:

- `YearMonth` text
- `ChannelKey` integer
- `SalesTarget` decimal
- `MarginTarget` decimal

### Relationships

Required relationships:

- `Sales[OrderDate]` -> `Date[Date]` active
- `Sales[ShipDate]` -> `Date[Date]` inactive
- `Sales[ProductKey]` -> `Product[ProductKey]`
- `Sales[CustomerKey]` -> `Customer[CustomerKey]`
- `Sales[StoreKey]` -> `Store[StoreKey]`
- `Sales[ChannelKey]` -> `Channel[ChannelKey]`
- `Sales[PromotionKey]` -> `Promotion[PromotionKey]`
- `Targets[ChannelKey]` -> `Channel[ChannelKey]`

Optional but useful:

- bridge `Targets[YearMonth]` to `Date[YearMonth]` if created as a proper relationship

## Measures

Create these measures in a dedicated measures table named `Measures` if convenient.

Required measures:

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

Metadata requirements:

- use display folders such as `Sales`, `Profitability`, `Targets`, `Time Intelligence`
- add descriptions to at least 5 measures

## Report Metadata and Settings

Configure report-level settings so `report get/set` has meaningful content:

- pages position not default, for example `Bottom`
- enhanced tooltips enabled
- cross-report drillthrough enabled
- inline exploration either explicitly enabled or disabled
- layout optimization explicitly set

## Theme and Styling

Create and apply one custom theme:

- clear brand name
- at least 6 `dataColors`
- non-default foreground/background/accent
- text class overrides

Also add intentional per-visual overrides:

- at least 3 redundant overrides that match the theme, for `theme audit --fix`
- at least 3 conflicting overrides that differ from theme values

## Images and Resources

Register at least two images:

- `logo.png` used on overview page
- `product-hero.png` used on one detail page

Also leave one unreferenced image resource in the project so `image prune` has work to do.

## Pages

Create the following pages.

### 1. `Executive Overview`

Purpose: dense but clean summary page.

Visuals:

- hero text box with title/subtitle
- image visual with company logo
- 4 KPI cards: `Revenue`, `Margin`, `Margin %`, `Orders`
- clustered column chart: `Date[MonthName]` by `Revenue`
- line chart overlay or combo chart showing `Revenue Target`
- donut chart by `Channel[ChannelName]`
- slicers:
  - `Date[Year]`
  - `Product[Category]`
  - `Customer[Region]`
- button group:
  - page navigation to `Product Detail`
  - page navigation to `Regional Detail`
  - bookmark navigation to a focused KPI state

Layout requirements:

- at least one grouped section suitable for `component create`
- at least one visual with custom title
- at least one visual hidden state override

### 2. `Product Detail`

Purpose: matrix, decomposition, and drillthrough target.

Visuals:

- matrix: Category > Subcategory > ProductName with `Revenue`, `Margin`, `Margin %`
- bar chart: top 10 products by `Revenue`
- scatter chart: `Revenue` vs `Margin %`, legend by `Brand`
- detail cards for selected product
- image visual for hero/product image

Requirements:

- page acts as drillthrough target on `Product[Category]` and `Product[ProductName]`
- include conditional formatting on matrix values
- include visual-level filter with top N

### 3. `Regional Detail`

Purpose: map-like or regional segmentation without requiring external map services.

Visuals:

- stacked bar by `Customer[Region]` and `Channel[ChannelName]`
- table by store with revenue metrics
- slicer for `Store[StoreType]`
- button back to overview

Requirements:

- include at least one interaction override, not just defaults

### 4. `Tooltip - Order Context`

Purpose: tooltip page.

Requirements:

- page type tooltip
- small canvas
- visuals showing `Revenue`, `Units`, `Margin %` for hovered context

### 5. `Hidden QA Page`

Purpose: hidden page used for lookup, page visibility, import/export, and map tests.

Requirements:

- hidden in view mode
- contain at least one textbox and one simple chart

## Bookmarks

Create at least 3 bookmarks:

- `Default View`
- `Focus On Online`
- `Hide Slicers`

Requirements:

- at least one bookmark changes display state
- at least one bookmark should preserve some non-display state so bookmark update logic is exercised

## Navigation

Include buttons with all three action patterns:

- page navigation
- bookmark navigation
- URL navigation

Also include one back button.

## Filters

Make sure the report contains all of the following somewhere:

- report-level categorical filter
- page-level filter
- visual-level filter
- include filter
- exclude filter
- range filter
- top N filter
- advanced filter using text operator such as `contains`

## Acceptance Checklist

The exported PBIP should satisfy all of these:

- custom theme present in `RegisteredResources`
- at least 5 pages, including 1 hidden and 1 tooltip page
- at least 15 visuals total
- at least 1 visual group with multiple children
- at least 2 bookmarks
- at least 2 buttons with actions
- at least 2 registered images, with 1 unreferenced
- at least 1 matrix and 1 table
- at least 1 combo or line/column comparison visual
- at least 1 drillthrough target
- at least 1 tooltip page binding
- measures and folders visible in the semantic model

