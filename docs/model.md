# Semantic Model Commands

The CLI can inspect and edit the semantic model stored as TMDL in the PBIP project.

## Inspect the model

```bash
pbi model tables
pbi model columns Sales
pbi model columns Sales --hidden
pbi model columns Sales --hidden-only
pbi model measures Sales
pbi model fields Sales
```

Use `pbi model fields <table>` when you need exact `Table.Field` references for binding, sorting, or filters.

## Format fields

Set a semantic-model format string on either a column or a measure:

```bash
pbi model format Sales.OrderDate "yyyy-mm-dd"
pbi model format Sales.TotalRevenue "$#,0"
pbi model format Sales.MarginPct "0.0%"
```

Use `--dry-run` to preview without writing TMDL:

```bash
pbi model format Sales.TotalRevenue "$#,0" --dry-run
```

## Hide and show columns

Visibility changes apply to columns only.

```bash
pbi model column hide Sales.InternalKey
pbi model column hide Sales.RowHash Sales.SourceId
pbi model column unhide Sales.InternalKey
```

## Manage measures

Create, inspect, update, and delete measures:

```bash
pbi model measure create Sales TotalRevenue "SUM ( Sales[Revenue] )" --format "$#,0"
pbi model measure edit Sales TotalRevenue "SUM ( Sales[NetRevenue] )"
pbi model measure get Sales TotalRevenue
pbi model measure delete Sales TotalRevenue
```

Expressions can also come from a file or stdin:

```bash
pbi model measure create Sales RevenuePct --from-file ./dax/revenue_pct.dax
cat ./dax/revenue_pct.dax | pbi model measure edit Sales RevenuePct
```

## Manage calculated columns

Create, inspect, update, and delete calculated columns:

```bash
pbi model column create Sales RevenueBand \
  "IF ( Sales[Revenue] >= 100000, \"High\", \"Standard\" )" \
  --type string

pbi model column edit Sales RevenueBand \
  "IF ( Sales[Revenue] >= 250000, \"Enterprise\", \"Standard\" )"

pbi model column get Sales.RevenueBand
pbi model column delete Sales RevenueBand
```

Calculated columns can also include format strings:

```bash
pbi model column create Sales MarginPct "DIVIDE ( Sales[Profit], Sales[Revenue] )" \
  --type double \
  --format "0.0%"
```

Source columns are intentionally protected:

- `pbi model column delete` only deletes calculated columns
- `pbi model column hide/unhide` works only on columns, not measures

## Declarative model apply

For larger changes, use `pbi model apply` with YAML:

```bash
pbi model apply ./model-changes.yaml
pbi model apply ./model-changes.yaml --dry-run
```

Example:

```yaml
measures:
  Sales:
  - name: Total Revenue
    expression: SUM ( Sales[Revenue] )
    format: "$#,0"
  - name: Margin %
    expression: DIVIDE ( [Total Profit], [Total Revenue] )
    format: "0.0%"

columns:
  Sales:
    InternalKey:
      hidden: true
    RevenueBand:
      expression: |
        IF ( Sales[Revenue] >= 100000, "High", "Standard" )
      dataType: string
    MarginPct:
      expression: |
        DIVIDE ( Sales[Profit], Sales[Revenue] )
      dataType: double
      format: "0.0%"
      hidden: false
```

Rules:

- `measures:` is a mapping of table name to a list of measure specs
- `columns:` is a mapping of table name to a mapping of column name to spec
- calculated columns require `expression` and `dataType`
- source columns cannot be created through `model apply`
- existing measures and calculated columns are updated in place when names match

## Recommended workflow

For one-off edits, use the imperative commands above. For several related changes, prefer:

1. `pbi model tables` / `pbi model columns` / `pbi model measures`
2. prepare a YAML file
3. `pbi model apply --dry-run`
4. `pbi model apply`
