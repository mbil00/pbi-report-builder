# PBIR Fixture Dataset

This dataset is designed specifically for building PBIP/PBIR fixture reports for this repository.

It is optimized for:

- relative date filters
- relative time filters
- Top N and VisualTopN filters
- advanced text filters
- include / exclude filters
- tuple filters
- blank / not-blank filters
- slicers, bookmarks, drillthrough, and navigation demos

## Files

- `Customers.csv`
- `Product.csv`
- `Date.csv`
- `Sales.csv`
- `RelativeTimeOffsets.csv`

## Recommended Table Names

Import the CSV files with these table names:

- `Customers`
- `Product`
- `Date`
- `Sales`
- `RelativeTimeOffsets`

## Recommended Relationships

- `Sales[CustomerID]` -> `Customers[CustomerID]`
- `Sales[ProductID]` -> `Product[ProductID]`
- `Sales[OrderDate]` -> `Date[Date]`

## Recommended Measures

Create these measures in `Sales`:

```DAX
Revenue = SUM ( Sales[Revenue] )
Quantity = SUM ( Sales[Quantity] )
Order Count = COUNTROWS ( Sales )
Average Order Value = DIVIDE ( [Revenue], [Order Count] )
```

## Relative Date

Use:

- `Date[Date]` for report/page/visual relative date filters
- `Sales[OrderDate]` if you want to test on the fact table directly

The `Date.csv` range intentionally spans dates before and after March 2026 so `InLast`, `InThis`, and `InNext` scenarios all have matching rows.

## Relative Time

There are two options:

### Option A: Dynamic and robust

Import `RelativeTimeOffsets.csv` and add this calculated column:

```DAX
DateTime = NOW() + DIVIDE ( RelativeTimeOffsets[OffsetMinutes], 1440.0 )
```

This is the best choice for relative time fixtures because it keeps the timestamps anchored to the current time when you build the report.

Good targets:

- last 15 minutes
- last 1 hour
- next 1 hour

### Option B: One-shot static testing

Use `Sales[OrderDateTime]` directly.

Those timestamps are centered around March 2026 and are useful if you are building the fixture immediately, but they are not ideal for long-term relative-time testing.

## Best Fields By Scenario

- Relative Date: `Date[Date]`
- Relative Time: `RelativeTimeOffsets[DateTime]`
- Top N target: `Customers[Region]` or `Product[Category]`
- Top N order-by: `[Revenue]` or `[Order Count]`
- Advanced text filters: `Product[ProductName]`, `Sales[OrderNote]`, `Customers[Segment]`
- Blank / not blank: `Product[Color]`, `Product[Size]`, `Sales[OrderNote]`
- Tuple filters: `Product[Color]` + `Product[Size]`

## Notes

- `Product.csv` intentionally contains blank `Color` and `Size` values.
- `Sales.csv` intentionally contains blank `OrderNote` values.
- `Sales.csv` contains enough variation by region, category, and revenue to make Top N and VisualTopN meaningful.
