---
name: pbi-modeling
description: "Power BI semantic model development with the `pbi` CLI — use when building or modifying data models, writing DAX measures, creating calculated columns, managing relationships/hierarchies, configuring RLS roles, perspectives, partitions, field parameters, or date tables. Triggers on: DAX expressions, measure creation, column formatting, model relationships, data modeling, semantic model, sort-by-column, display folders, calculated tables, time intelligence, model YAML apply/export, field parameters, table rename."
---

# Power BI Semantic Model Development

You are working with a Power BI PBIP project's semantic model using the `pbi` CLI. The model defines tables, columns, measures, relationships, and hierarchies that power the report visuals.

## Workflow Priority

1. **Declarative (preferred for bulk changes):** Write YAML, then `pbi model apply`
2. **Imperative (for individual items):** `pbi model measure create`, `pbi model column set`, etc.

## Step 1: Discover the Model

Before making changes, understand what exists:

```bash
pbi map --model                           # full model overview
pbi model table list                      # all tables
pbi model fields Sales                    # columns + measures for a table
pbi model search "revenue"               # find fields by keyword across all tables
pbi model relationship list               # all relationships
pbi model path Sales Products             # join path between two tables
pbi model measure get Sales.TotalRevenue  # inspect a measure's DAX
pbi model column get Sales.OrderDate      # inspect column metadata
pbi model get                             # model-level settings
```

## Step 2: Measures

Measures are the core of any Power BI model. The CLI handles creation, editing, formatting, and dependency-aware renaming.

### Create measures

```bash
pbi model measure create Sales "Total Revenue" "SUM(Sales[Revenue])" --format "#,0"
pbi model measure create Sales "YoY Growth" \
  "VAR CurrentYear = [Total Revenue]
   VAR PriorYear = CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(Date[Date]))
   RETURN DIVIDE(CurrentYear - PriorYear, PriorYear)" \
  --format "0.0%"
```

### Edit and manage measures

```bash
pbi model measure edit Sales "Total Revenue" "SUMX(Sales, Sales[Qty] * Sales[Price])"
pbi model measure set Sales.TotalRevenue description="Sum of all revenue" displayFolder="KPIs"
pbi model measure get Sales.TotalRevenue         # full definition
pbi model measure list Sales                     # list measures (--full for complete DAX)
pbi model measure delete Sales "Total Revenue" --force
```

### Rename with cascading DAX references

```bash
pbi model measure rename Sales "Total Rev" "Total Revenue"
```

This automatically updates all `[Total Rev]` and `Sales[Total Rev]` references across every measure in the model.

### Dependency analysis

```bash
pbi model deps Sales.TotalRevenue                # what does this measure reference?
pbi model deps Sales.TotalRevenue --reverse      # what references this measure?
```

## Step 3: Columns

### Calculated columns

```bash
pbi model column create Sales Status "IF([Revenue]>1000, \"High\", \"Low\")" --type string
pbi model column edit Sales Status "IF([Revenue]>5000, \"Premium\", \"Standard\")"
pbi model column delete Sales Status --force
```

### Column properties

```bash
# Writable properties: description, displayFolder, sortByColumn, summarizeBy, dataCategory, formatString
pbi model column set Sales.OrderDate formatString="dd/MM/yyyy"
pbi model column set Sales.Revenue summarizeBy=Sum
pbi model column set Products.Name sortByColumn=Products.SortOrder
pbi model column set Geography.City dataCategory=City

# Hide/unhide from report view
pbi model column hide Sales.InternalId
pbi model column unhide Sales.InternalId

# Bulk hide by pattern
pbi model column hide --table Sales --pattern "ID$"        # hide all columns ending in "ID"
pbi model column unhide --table Sales --pattern "ID$"
```

### Format columns and measures

Use `formatString` via `set` or `--format` on create:

```bash
pbi model column set Sales.Revenue formatString="#,0"
pbi model column set Sales.OrderDate formatString="dd/MM/yyyy"
pbi model measure set Sales.MarginPct formatString="0.0%"
```

## Step 4: Relationships

```bash
pbi model relationship list
pbi model relationship create Sales.ProductID Products.ProductID
pbi model relationship create Sales.ProductID Products.ProductID --cross-filter both
pbi model relationship create Sales.ProductID Products.ProductID --inactive
pbi model relationship set Sales.ProductID Products.ProductID crossFilteringBehavior=bothDirections
pbi model relationship delete Sales.ProductID Products.ProductID --force
```

### Validate relationships

```bash
pbi model check                # find bidirectional cross-filters, auto-detected issues, missing relationships
pbi model path Sales Products  # verify join path exists between tables
```

## Step 5: Hierarchies

```bash
pbi model hierarchy list Date
pbi model hierarchy create Date "Calendar" Year Quarter Month
pbi model hierarchy delete Date "Calendar" --force
```

## Step 6: Date Table & Time Intelligence

```bash
pbi model table set Date dateTable=Date              # mark Date[Date] as the date table (also set via table set)
pbi model set timeIntelligence=off                   # disable auto date/time tables
```

Disabling auto date/time removes the local date tables Power BI creates for every date column — cleaner model, faster refresh.

## Step 7: Tables

```bash
pbi model table list
pbi model table get Date                             # metadata including date-table status
pbi model table create "Calendar" "CALENDARAUTO()"   # calculated table
pbi model table rename OldName NewName               # rename a table
pbi model table set Date dateTable=Date              # mark as date table
```

## Step 8: Advanced Model Features

### Row-Level Security (RLS)

```bash
pbi model role list
pbi model role create "Finance Readers"
pbi model role set "Finance Readers" permission=readRefresh
pbi model role filter set "Finance Readers" Department 'Department[Division] = "Corporate"'
pbi model role member create "Finance Readers" finance@example.com --type group
pbi model role filter clear "Finance Readers" Department
pbi model role delete "Finance Readers" --force
```

### Perspectives

```bash
pbi model perspective list
pbi model perspective create "Exec View" --include-all Sales --measure Sales.Revenue
pbi model perspective set "Exec View" --column Date.Year --hierarchy Date.Calendar
pbi model perspective get "Exec View"
pbi model perspective delete "Exec View" --force
```

### Partitions

```bash
pbi model partition list
pbi model partition get Sales Sales
pbi model partition create Sales Sales 'ROW("x", 1)' --source-type calculated
pbi model partition set Sales Sales sourceType=m --from-file ./partitions/sales.m
pbi model partition delete Sales Sales --force
```

### Annotations

```bash
pbi model annotation list
pbi model annotation get PBI_QueryOrder
pbi model annotation set PBI_ProTooling '["DevMode"]'
pbi model annotation delete PBI_ProTooling --force
```

## Model Apply — Bulk Changes from YAML

For multiple changes at once, the declarative approach is faster and less error-prone.

### Round-trip workflow

```bash
pbi model export -o model.yaml        # capture current state
# edit model.yaml
pbi model apply model.yaml --dry-run  # preview changes
pbi model apply model.yaml            # apply
```

### YAML structure

```yaml
# Model-level settings
model:
  timeIntelligence: false

# Table settings
tables:
  Date:
    dataCategory: Time
    dateTable: Date

# Measures — grouped by table
measures:
  Sales:
  - name: Total Revenue
    expression: SUM(Sales[Revenue])
    format: "#,0"
    description: Sum of all revenue
    displayFolder: KPIs

  - name: YoY Growth
    expression: |
      VAR CurrentYear = [Total Revenue]
      VAR PriorYear = CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(Date[Date]))
      RETURN DIVIDE(CurrentYear - PriorYear, PriorYear)
    format: "0.0%"
    displayFolder: KPIs

# Columns — table-keyed mapping
columns:
  Sales:
    Revenue:
      format: "#,0"
      summarizeBy: Sum
      description: Transaction revenue amount
    OrderDate:
      format: dd/MM/yyyy
    InternalId:
      hidden: true
  Products:
    Name:
      sortByColumn: SortOrder

# Relationships
relationships:
- from: Sales.ProductID
  to: Products.ProductID
  crossFilteringBehavior: oneDirection
  isActive: true

# Hierarchies — table-keyed
hierarchies:
  Date:
  - name: Calendar
    levels: [Year, Quarter, Month]

# Field parameters — name-keyed
fieldParameters:
  Metric Selection:
    fields:
    - field: Sales.Revenue
      label: Revenue
    - field: Sales.Profit
      label: Profit
    - field: Sales.OrderCount
      label: Orders
```

### Field parameters (imperative)

```bash
pbi model field-parameter create "Metric Selection" Sales.Revenue Sales.Profit \
  --labels Revenue Profit
```

## DAX Patterns

Common patterns for reference when authoring measures:

### Aggregation
```dax
Total Revenue = SUM(Sales[Revenue])
Avg Order Value = AVERAGE(Sales[OrderAmount])
Order Count = COUNTROWS(Sales)
Distinct Customers = DISTINCTCOUNT(Sales[CustomerID])
```

### Time intelligence (requires a marked date table)
```dax
YTD Revenue = TOTALYTD([Total Revenue], Date[Date])
Prior Year = CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(Date[Date]))
MoM Change = [Total Revenue] - CALCULATE([Total Revenue], DATEADD(Date[Date], -1, MONTH))
```

### Conditional / status
```dax
Status Color =
  SWITCH(TRUE(),
    [Margin %] >= 0.3, "#107C10",
    [Margin %] >= 0.15, "#FFB900",
    "#D13438"
  )
```

### Division safety
```dax
Margin % = DIVIDE(SUM(Sales[Profit]), SUM(Sales[Revenue]))
```

Always use `DIVIDE()` instead of `/` — it returns BLANK instead of error on division by zero.

## Common Pitfalls

- **Missing date table:** Time intelligence functions (`TOTALYTD`, `SAMEPERIODLASTYEAR`) require `pbi model table set Date dateTable=Date` first
- **Ambiguous column references:** Use `Table[Column]` syntax in DAX, not just `[Column]`, to avoid ambiguity across tables
- **sortByColumn:** The sort column must be in the same table as the column being sorted
- **Renaming measures:** Always use `pbi model measure rename` — it cascades DAX references. Manual rename leaves broken references
- **Format strings:** Use quotes around format strings with special characters: `--format "#,0.00"`
