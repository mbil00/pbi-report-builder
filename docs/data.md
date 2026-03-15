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
pbi model tables
pbi model columns Sales
pbi model columns Sales --hidden
pbi model measures Sales
pbi model fields Sales
```

Write-side semantic-model editing is documented in [Semantic Model Commands](model.md), including:

- `pbi model format`
- `pbi model column hide|show|create|edit|get|delete`
- `pbi model measure create|edit|show|delete`
- `pbi model apply`

## Filter Scope

Filters use positional scope:

```bash
pbi filter list report
pbi filter list page "Sales Overview"
pbi filter list visual "Sales Overview" revenueChart
```

## Add Filters

### Categorical / Include / Exclude

```bash
pbi filter add report Product.Category --mode categorical --value Bikes
pbi filter add report Product.Category --mode include --value Bikes --value Accessories
pbi filter add page "Sales Overview" Product.Category --mode exclude --value Obsolete
```

### Range

```bash
pbi filter add report Sales.Revenue --mode range --min 1000 --max 50000
pbi filter add page "Sales Overview" Sales.OrderDate --mode range --min "2024-01-01" --max "2024-12-31"
```

### Top N

```bash
pbi filter add report Customers.Region --mode topn --topn 7 --topn-by Sales.TotalRevenue --direction top
pbi filter add report Customers.Region --mode topn --topn 5 --topn-by Sales.TotalRevenue --direction bottom
```

### Relative Date / Time

```bash
pbi filter add report Date.Date --mode relative --operator InLast --count 7 --unit Days
pbi filter add report Date.Date --mode relative --operator InNext --count 1 --unit Quarters --no-include-today
pbi filter add report Date.DateTime --mode relative --operator InLast --count 15 --unit Minutes
```

### Tuple

```bash
pbi filter add report --mode tuple --row "Product.Color=Red,Product.Size=Large"
pbi filter add page "Sales Overview" --mode tuple \
  --row "Product.Color=Red,Product.Size=Large" \
  --row "Product.Color=Blue,Product.Size=Medium"
```

## Remove Filters

```bash
pbi filter remove report Product.Category
pbi filter remove page "Sales Overview" Sales.Revenue
pbi filter remove visual "Sales Overview" revenueChart Customers.Region
```
