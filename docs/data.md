# Data & Filters

## Data Binding Commands

### pbi visual bind

Bind a column (dimension) or measure (fact) to a visual's data role.

```bash
pbi visual bind <page> <visual> <role> <Table.Field>
pbi visual bind <page> <visual> <role> <Table.Field> --measure    # force measure type
```

Field type (column vs measure) is auto-detected from the semantic model. Use `--measure` / `-m` to override.

```bash
pbi visual bind "Sales" chart Category Product.Category
pbi visual bind "Sales" chart Y Sales.Revenue
pbi visual bind "Sales" chart Y Sales.TotalOrders --measure
pbi visual bind "Sales" table Values Product.Name
pbi visual bind "Sales" scatter X Sales.Revenue Y Sales.Profit
```

### pbi visual unbind

Remove data bindings from a visual. Omit the field to remove the entire role.

```bash
pbi visual unbind <page> <visual> <role>                    # remove entire role
pbi visual unbind <page> <visual> <role> <Table.Field>      # remove specific field
```

```bash
pbi visual unbind "Sales" chart Series
pbi visual unbind "Sales" chart Y Sales.TotalOrders
```

### pbi visual bindings

List all data bindings on a visual.

```bash
pbi visual bindings <page> <visual>
```

## Semantic Model Commands

### pbi model tables

List tables in the semantic model.

```bash
pbi model tables
```

### pbi model columns

List columns (dimensions) in a table.

```bash
pbi model columns <table>
pbi model columns <table> --hidden      # include hidden columns
```

### pbi model measures

List measures (facts) in a table.

```bash
pbi model measures <table>
```

### pbi model fields

List all fields (columns + measures) for use with `visual bind`.

```bash
pbi model fields <table>
```

## Filter Commands

Filters can be applied at three levels:
- **Report-level** (default): omit `--page` and `--visual`
- **Page-level**: pass `--page`
- **Visual-level**: pass `--page` and `--visual`

### pbi filter list

```bash
pbi filter list                                    # report-level
pbi filter list --page "Sales"                     # page-level
pbi filter list --page "Sales" --visual chart      # visual-level
```

### pbi filter add

Add a filter. Exactly one filter type per command.

**Categorical filter** — match specific values:

```bash
pbi filter add Product.Category --values "Bikes,Accessories"
pbi filter add Product.Category --values "Bikes" --page "Sales"
pbi filter add Product.Category --values "Bikes" --page "Sales" --visual chart
```

**Range filter** — numeric or date range:

```bash
pbi filter add Sales.Revenue --min 1000 --max 50000
pbi filter add Sales.Revenue --min 1000
pbi filter add Sales.OrderDate --min "2024-01-01" --max "2024-12-31"
```

**Top N filter** — top or bottom N items by a measure:

```bash
pbi filter add Product.Category --topn 10 --topn-by Sales.Revenue
pbi filter add Product.Category --topn 5 --topn-by Sales.Revenue --bottom
```

**Relative date filter** — dynamic date ranges:

```bash
pbi filter add Sales.OrderDate --relative "InLast 7 Days"
pbi filter add Sales.OrderDate --relative "InThis 1 Months"
pbi filter add Sales.OrderDate --relative "InNext 2 Weeks" --no-include-today
```

Relative date operators: `InLast`, `InThis`, `InNext`
Time units: `Days`, `Weeks`, `Months`, `Quarters`, `Years`

**Options:**

| Option | Description |
|--------|-------------|
| `--values`, `-v` | Comma-separated values for categorical filter |
| `--min` | Minimum value for range filter |
| `--max` | Maximum value for range filter |
| `--topn` | Top N items count |
| `--topn-by` | Order-by field for Top N (`Table.Measure`) |
| `--bottom` | Use Bottom N instead of Top N |
| `--relative` | Relative date: `"Operator Count Unit"` |
| `--include-today` / `--no-include-today` | Include today in relative date (default: yes) |
| `--page` | Apply at page level |
| `--visual` | Apply at visual level (requires `--page`) |
| `--hidden` | Hide filter in view mode |
| `--locked` | Lock filter in view mode |
| `--measure`, `-m` | Treat field as a measure |

### pbi filter remove

```bash
pbi filter remove <Table.Field>                                    # report-level
pbi filter remove <Table.Field> --page "Sales"                     # page-level
pbi filter remove <Table.Field> --page "Sales" --visual chart      # visual-level
```

```bash
pbi filter remove Product.Category
pbi filter remove Sales.Revenue --page "Sales"
```
