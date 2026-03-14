# Agent Workflows

## Recommended Pattern

1. Inspect with `get`, `list`, or `map`.
2. Mutate with `set` using `key=value`.
3. Use exact page names and friendly visual names for write commands.
4. Validate with `pbi validate`.

## Common Flows

### Page export / apply

```bash
pbi page export "Sales Overview" --output sales.yaml
pbi apply sales.yaml --page "Sales Overview"
pbi apply sales.yaml --page "Sales Overview" --overwrite
```

### Styling

```bash
pbi visual set "Sales Overview" revenueChart title.show=true title.text="Revenue"
pbi visual set-all "Sales Overview" background.show=true background.color="#FFFFFF"
pbi visual paste-style "Sales Overview" revenueChart profitChart --scope all
```

### Filters

```bash
pbi filter add report Product.Category --mode include --value Bikes --value Accessories
pbi filter add report Sales.Revenue --mode range --min 1000 --max 50000 --locked
pbi filter add report Customers.Region --mode topn --topn 5 --topn-by Sales.TotalRevenue --direction top
pbi filter add report --mode tuple --row "Product.Color=Red,Product.Size=Large"
```

### Bookmarks and interactions

```bash
pbi bookmark create "Minimal View" "Sales Overview" --hide detailTable
pbi bookmark set "Minimal View" --show detailTable

pbi interaction set "Sales Overview" regionSlicer revenueChart --mode NoFilter
pbi interaction clear "Sales Overview" regionSlicer revenueChart
```

### Drillthrough and tooltip pages

```bash
pbi page drillthrough set "Product Details" Product.Category
pbi page tooltip set "Sales Tooltip" Product.Category --width 400 --height 300
```
