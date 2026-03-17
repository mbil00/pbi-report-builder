# Data & Filters

## Data Binding

```bash
pbi visual bind "Sales Overview" revenueChart Category Product.Category --field-type auto
pbi visual bind "Sales Overview" revenueChart Y Sales.TotalRevenue --field-type measure
pbi visual unbind "Sales Overview" revenueChart Category
pbi visual unbind "Sales Overview" revenueChart Y Sales.TotalRevenue
pbi visual bindings "Sales Overview" revenueChart
```

`--field-type` is the canonical field typing flag across binding, sorting, and filters.

## Semantic Model

```bash
pbi model table list
pbi model column list Sales
pbi model column list Sales --hidden
pbi model measure list Sales
pbi model fields Sales
```

Write-side semantic-model editing is documented in [Semantic Model Commands](model.md), including:

- `pbi model format`
- `pbi model column hide|unhide|create|edit|get|delete`
- `pbi model measure create|edit|get|delete`
- `pbi model apply`

## Filter Scope

Scope is inferred from `--page` and `--visual` flags. Default is report level.

```bash
pbi filter list                                         # report level
pbi filter list --page "Sales Overview"                 # page level
pbi filter list --page "Sales Overview" --visual chart1 # visual level
```

## Add Filters

### Categorical / Include / Exclude

```bash
pbi filter create Product.Category --mode categorical --value Bikes
pbi filter create Product.Category --mode include --value Bikes --value Accessories
pbi filter create Product.Category --page "Sales Overview" --mode exclude --value Obsolete
```

### Range

```bash
pbi filter create Sales.Revenue --mode range --min 1000 --max 50000
pbi filter create Sales.OrderDate --page "Sales Overview" --mode range --min "2024-01-01" --max "2024-12-31"
```

### Top N

```bash
pbi filter create Customers.Region --mode topn --topn 7 --topn-by Sales.TotalRevenue --direction top
pbi filter create Customers.Region --mode topn --topn 5 --topn-by Sales.TotalRevenue --direction bottom
```

### Relative Date / Time

```bash
pbi filter create Date.Date --mode relative --operator InLast --count 7 --unit Days
pbi filter create Date.Date --mode relative --operator InNext --count 1 --unit Quarters --no-include-today
pbi filter create Date.DateTime --mode relative --operator InLast --count 15 --unit Minutes
```

### Tuple

```bash
pbi filter create --mode tuple --row "Product.Color=Red,Product.Size=Large"
pbi filter create --page "Sales Overview" --mode tuple \
  --row "Product.Color=Red,Product.Size=Large" \
  --row "Product.Color=Blue,Product.Size=Medium"
```

## Delete Filters

```bash
pbi filter delete Product.Category
pbi filter delete Sales.Revenue --page "Sales Overview"
pbi filter delete Customers.Region --page "Sales Overview" --visual revenueChart
```
