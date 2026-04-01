# Semantic Model Commands

The CLI can inspect and edit the semantic model stored as TMDL in the PBIP project.

## Investigation helpers

For schema or authoring investigations, you can generate a file-location trace for the semantic model:

```bash
uv run python scripts/extract_tmdl_trace.py --project-root .
uv run python scripts/inspect_tmdl_trace.py --project-root . --ref measure:Sales.Revenue
uv run python scripts/inspect_tmdl_trace.py --project-root . --ref relationship:Sales.CustomerID->Customers.CustomerID
```

The extractor writes `schema-analysis/generated/tmdl.trace.json` by default. The manifest indexes TMDL entities by ref and records their source file, line numbers, and a short snippet.

Common ref formats:

- `table:Sales`
- `column:Sales.Region`
- `calculatedColumn:Sales.Bucket`
- `measure:Sales.Revenue`
- `hierarchy:Date.Calendar`
- `partition:Sales.Sales`
- `annotation:__PBI_TimeIntelligenceEnabled`
- `relationship:Sales.CustomerID->Customers.CustomerID`
- `role:Finance Readers`
- `perspective:Exec View`

## Inspect the model

```bash
pbi model table list
pbi model column list Sales
pbi model column list Sales --hidden
pbi model column list Sales --hidden-only
pbi model measure list Sales
pbi model fields Sales
```

Use `pbi model fields <table>` when you need exact `Table.Field` references for binding, sorting, or filters.

Inspect model or table settings:

```bash
pbi model get
pbi model table get Date
```

Set a date table and disable auto date/time:

```bash
pbi model table set Date dateTable=Date
pbi model set timeIntelligence=off
```

Manage perspectives and RLS roles:

```bash
pbi model annotation list
pbi model annotation set PBI_ProTooling '["DevMode"]'
pbi model perspective list
pbi model perspective create "Exec View" --include-all Sales --measure Sales.Revenue
pbi model role list
pbi model role create "Finance Readers"
pbi model role filter set "Finance Readers" Department 'Department[Division] = "Corporate"'
pbi model role member create "Finance Readers" finance@example.com --type group
pbi model partition list
pbi model partition get Sales Sales
```

## Relationships

List all relationships in the semantic model, or filter by table:

```bash
pbi model relationship list
pbi model relationship list --from Sales
pbi model relationship list --to Customers
pbi model relationship list --json
```

Find the shortest relationship path between two tables:

```bash
pbi model path Sales Customers
# Path (1 hop):
#   Sales.CustomerID → Customers.CustomerID

pbi model path Product Customers
# Path (2 hops):
#   Sales.ProductID → Product.ProductID
#   Sales.CustomerID → Customers.CustomerID
```

Use this to verify cross-table references before building visuals. `pbi validate` will also warn about visuals referencing tables with no relationship path.

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
cat model-changes.yaml | pbi model apply
cat model-changes.yaml | pbi model apply --dry-run
```

`pbi model apply` also accepts `-` to read YAML from stdin explicitly.

Example:

```yaml
model:
  timeIntelligence: false

tables:
  Date:
    dataCategory: Time
    dateTable: Date

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

- `model:` currently supports `timeIntelligence: true|false`
- `model.annotations:` is a mapping of model annotation name to raw TMDL literal value
- `tables:` supports table-level metadata such as `dataCategory` and `dateTable`
- `measures:` is a mapping of table name to a list of measure specs
- `columns:` is a mapping of table name to a mapping of column name to spec
- `partitions:` is a mapping of table name to a list of partition specs
- `roles:` is a mapping of role name to `permission`, `filters`, and `members`
- `perspectives:` is a mapping of perspective name to table membership specs
- calculated columns require `expression` and `dataType`
- source columns cannot be created through `model apply`
- existing measures and calculated columns are updated in place when names match

Role example:

```yaml
roles:
  Finance Readers:
    permission: read
    filters:
      Department: Department[Division] = "Corporate"
    members:
    - name: finance@example.com
    - name: finance-group@example.com
      type: group
```

Partition example:

```yaml
partitions:
  Sales:
  - name: Sales
    sourceType: m
    mode: import
    source: |
      let
          Source = Csv.Document(File.Contents("sales.csv"))
      in
          Source
```

Model annotation example:

```yaml
model:
  timeIntelligence: false
  annotations:
    PBI_ProTooling: '["DevMode"]'
```

## Recommended workflow

For one-off edits, use the imperative commands above. For several related changes, prefer:

1. `pbi model table list` / `pbi model column list` / `pbi model measure list`
2. prepare a YAML file or generate YAML to stdout
3. `pbi model apply ./model-changes.yaml --dry-run` or pipe into `pbi model apply --dry-run`
4. `pbi model apply ./model-changes.yaml` or pipe into `pbi model apply`
