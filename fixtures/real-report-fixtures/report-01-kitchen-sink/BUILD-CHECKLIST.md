# Build Checklist: Report 01 Kitchen Sink

## Goal

Create a PBIP report fixture that exercises the widest practical report-authoring surface of `pbi-report-builder`.

Dataset location:

- `/home/mbil/Projects/pbi-report-builder/fixtures/real-report-fixtures/report-01-kitchen-sink/data`

CSV files to import:

- `Channel.csv`
- `Customer.csv`
- `Date.csv`
- `Product.csv`
- `Promotion.csv`
- `Sales.csv`
- `Store.csv`
- `Targets.csv`

## 1. Create The Base PBIP Project

1. Open Power BI Desktop.
2. Create a new PBIP project named something like `KitchenSinkFixture`.
3. Save it as PBIP immediately so the model/report artifacts exist from the start.
4. Record the exact Power BI Desktop version used.

## 2. Load Data

Import these CSVs from `/home/mbil/Projects/pbi-report-builder/fixtures/real-report-fixtures/report-01-kitchen-sink/data`:

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
