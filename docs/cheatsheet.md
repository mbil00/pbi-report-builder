# PBI CLI — Cheatsheet

Quick reference for the most common tasks. The CLI uses a consistent grammar — learn one pattern, apply it everywhere.

---

## Core Grammar

```
pbi <object> <verb> <target> [key=value...] [--flags]
```

**Verbs work the same across all objects:**

| Verb | What it does | Works on |
|------|-------------|----------|
| `list` | Show all items | page, visual, filter, interaction, bookmark, style, component, image, model tables/columns/measures/fields |
| `get` | Show one item's details | page, visual, report, bookmark, style, component, model measure, model column |
| `set` | Change properties | page, visual, report, interaction |
| `set-all` | Change properties in bulk | page (all pages), visual (all visuals) |
| `create` | Add new item | page, visual, filter, bookmark, style, component, image, model measure, model column |
| `delete` | Remove item (prompts unless `--force`) | page, visual, filter, style, component, model measure, model column |
| `clear` | Remove configuration | visual sort, visual format, interaction, page drillthrough, page tooltip |
| `apply` | Apply from YAML/preset | top-level, model, style, component, page template, theme |
| `export` | Export to YAML/JSON | page (YAML), theme (JSON) |

**Common flags across all commands:**

| Flag | Meaning | Available on |
|------|---------|-------------|
| `--dry-run` | Preview without writing | apply, model apply, set-all, visual set, style apply, component apply, theme migrate |
| `--json` | Machine-readable output | All list commands |
| `--force, -f` | Skip confirmation | All delete commands |
| `--page` | Narrow scope to one page | filter, visual set-all, apply |
| `--all-pages` | Apply across every page | visual set-all, visual column |
| `-p, --project` | Specify project path | Every command |

---

## Pages

```bash
pbi page list                                    # list all pages
pbi page get "Overview"                          # show page properties
pbi page create "Detail View"                    # create new page
pbi page copy "Overview" "Overview Copy"         # duplicate with all visuals
pbi page delete "Draft" --force                  # delete page

# Properties use key=value syntax — same as visual set
pbi page set "Overview" displayName="Dashboard"  # rename page
pbi page set "Overview" width=1920 height=1080   # resize page
pbi page set-all background.color="#F5F5F5"      # set background on ALL pages
pbi page set-all background.color="#FFF" --exclude "Hidden"  # skip pages matching name

pbi page reorder "Overview" "Detail" "Admin"     # set page order
pbi page set-active "Overview"                   # set default open page
pbi page export                                  # export all pages as YAML
pbi page export "Overview" -o overview.yaml      # export one page
```

**Page types (drillthrough & tooltip):**
```bash
pbi page drillthrough set "Detail" Products.Category   # make drillthrough page
pbi page drillthrough get "Detail"                     # inspect drillthrough fields
pbi page drillthrough clear "Detail"                    # revert to normal page
pbi page tooltip set "Card Tip"                         # make tooltip page
pbi page tooltip get "Card Tip"                         # inspect tooltip settings
pbi page tooltip clear "Card Tip"                       # revert to normal page
```

---

## Visuals

```bash
pbi visual list "Overview"                        # list visuals on page
pbi visual create "Overview" clusteredBarChart    # create visual
pbi visual create "Overview" cardVisual --name kpi1 --title "Revenue"
pbi visual create "Overview" clusteredColumnChart --name revenueChart \
  --bind Category=Date.Month --bind Y=Sales.Revenue --sort Date.Month
pbi visual create "Overview" clusteredColumnChart --name revenueChart \
  --bind Category=Date.Month --bind Y=Sales.Revenue --preset chart
pbi visual create "Overview" donutChart --name revenueMix \
  --bind Category=Sales.Channel --bind Y=Sales.Revenue --preset chart
pbi visual create "Overview" slicer --name yearSlicer --bind Values=Date.Year --preset slicer
pbi visual create "Overview" clusteredColumnChart --name monthlyRevenue \
  --bind Category=Date.MonthName --bind Y=Sales.Revenue   # auto-sorts via sortByColumn
pbi visual rename "Overview" kpi1 "revenueCard"  # give visual a friendly name
pbi visual copy "Overview" chart1 --to-page "Detail"   # copy to another page
pbi visual delete "Overview" chart1 --force       # delete visual

# visual types shows available types and their data roles
pbi visual types                                  # list all visual types
pbi visual types clusteredBarChart                # show roles for one type
```

**Properties — same key=value pattern as pages:**
```bash
pbi visual set "Overview" myChart title.show=true title.text="Sales"
pbi visual set "Overview" myChart background.color="#FFFFFF" border.show=true

# Bulk set across visuals — the most powerful styling command
pbi visual set-all --page "Overview" border.show=false         # all visuals on page
pbi visual set-all --all-pages background.color="#FFFFFF"      # entire report
pbi visual set-all --all-pages title.fontSize=12 --where title.show=true  # conditional

# Chart-specific properties — auto-resolved from PBI schema (no chart: prefix needed)
pbi visual set "Overview" myChart legend.show=false legend.position=Top
pbi visual set "Overview" myChart categoryAxis.show=true valueAxis.show=true

# Discover properties — use --visual-type to see all schema-derived properties
pbi visual properties                                         # list registered properties
pbi visual properties --visual-type cardVisual                # all properties for card visuals
pbi visual properties --visual-type clusteredBarChart --match "legend"  # search
pbi visual objects "Overview" myChart                         # inspect current chart objects
```

**Data bindings:**
```bash
pbi visual bind "Overview" myChart Category Products.Category
pbi visual bind "Overview" myChart Y Facts.Revenue
pbi visual unbind "Overview" myChart Category     # remove binding
pbi visual bindings "Overview" myChart            # list current bindings
```

**Sort, format, layout:**
```bash
pbi visual sort set "Overview" myChart Products.Revenue --direction desc
pbi visual sort clear "Overview" myChart

# Column formatting (tables/matrices) — resize, rename, format individual columns
pbi visual column "Overview" myTable                          # list columns
pbi visual column "Overview" myTable "Revenue" --width 120    # resize column
pbi visual column "Overview" myTable "Revenue" --rename "Rev ($)" --align right

# Conditional formatting
pbi visual format get "Overview" myTable                     # show existing CF
pbi visual format set "Overview" myTable values.fontColor \
  --mode rules --source "Devices.ComplianceState" \
  --rule "Compliant=#2B7A4B" --rule "NonCompliant=#B83B3B" --else-color "#605E5C"
pbi visual format set "Overview" myTable values.backColor \
  --mode gradient --source "Table.Score" \
  --min-color "#FFFFFF" --min-value 0 --max-color "#FFEBEE" --max-value 100
pbi visual format clear "Overview" myTable values.fontColor  # remove CF

# Audit style consistency across pages
pbi visual audit                                             # all types, all pages
pbi visual audit --visual-type slicer                        # just slicers
pbi visual audit --visual-type cardVisual --json             # machine-readable

# Arrange visuals spatially
pbi visual arrange row "Overview" card1 card2 card3 --gap 16    # horizontal row
pbi visual arrange grid "Overview" card1 card2 card3 card4 --columns 2  # 2-col grid
pbi visual arrange align "Overview" card1 card2 --distribute horizontal  # even spacing

# Position calculator — get coordinates without having visuals yet
pbi calc row 4 --width 1280 --margin 16 --gap 12     # 4 items in a row
pbi calc grid 6 --columns 3 --margin 16              # 6 items in 3-col grid
```

---

## YAML Apply — Declarative Workflow

The star feature. Define pages fully in YAML, apply in one shot.

```bash
pbi apply page.yaml                    # apply YAML (additive)
pbi apply page.yaml --dry-run          # preview what would change
pbi apply page.yaml --overwrite        # full reconciliation (deletes unlisted visuals)
pbi apply page.yaml --page "Overview"  # apply only one page from multi-page YAML
pbi diff page.yaml                     # property-by-property diff before applying
```

**Round-trip workflow:**
```bash
pbi page export "Overview" -o overview.yaml   # 1. export
# edit overview.yaml                          # 2. edit
pbi diff overview.yaml                        # 3. review
pbi apply overview.yaml                       # 4. apply
```

**YAML supports:** visuals, bindings, properties, filters, interactions, conditional formatting, sort, KPI cards, textbox content, bookmarks, drillthrough/tooltip pages, styles, and raw PBIR passthrough.

---

## Semantic Model

```bash
pbi model table list                          # list all tables
pbi model column list Sales                   # list columns (shows calculated vs source)
pbi model measure list Facts                  # list measures (use --full for complete DAX)
pbi model fields Sales                        # list both columns and measures
pbi model search "revenue"                    # search across all tables
pbi model get                                 # model-level settings
pbi model table get Date                      # table metadata incl. date-table status
pbi model relationship list                   # list relationships
pbi model path Sales Products                 # show join path between tables

# Format — same command for columns and measures
pbi model format "Facts.Revenue" "#,0"
pbi model format "Sales.OrderDate" "dd/mm/yyyy"

# Time intelligence / date table
pbi model table set Date dateTable=Date       # mark Date[Date] as the date table
pbi model set timeIntelligence=off            # disable auto date/time and remove local date tables
```

**Measures:**
```bash
pbi model measure create Sales "Total Rev" "SUM(Sales[Revenue])" --format "#,0"
pbi model measure edit Sales "Total Rev" "SUMX(Sales, Sales[Qty] * Sales[Price])"
pbi model measure get Sales "Total Rev"       # show full definition
pbi model measure delete Sales "Total Rev" --force
```

**Calculated columns:**
```bash
pbi model column create Sales Status "IF([Revenue]>1000, \"High\", \"Low\")" --type string
pbi model column edit Sales Status "IF([Revenue]>5000, \"Premium\", \"Standard\")"
pbi model column get Sales Status              # also works: pbi model column get Sales.Status
pbi model column delete Sales Status --force
pbi model column hide Sales.InternalId         # hide columns from report view
pbi model column unhide Sales.InternalId
```

**Model apply — bulk changes from YAML:**
```bash
pbi model apply model.yaml                     # create/update measures and columns
pbi model apply model.yaml --dry-run           # preview changes

# model.yaml can also include:
# model:
#   timeIntelligence: false
# tables:
#   Date:
#     dataCategory: Time
#     dateTable: Date
```

---

## Filters

Scope narrows with `--page` and `--visual` (visual requires page).

```bash
pbi filter list                                          # report-level filters
pbi filter list --page "Overview"                        # page-level
pbi filter list --page "Overview" --visual myChart       # visual-level

pbi filter create Sales.Region --value "North" "South"   # categorical (report-level)
pbi filter create Sales.Region --value "East" --page "Overview"       # page-level
pbi filter create Sales.Revenue --min 100 --max 999      # range filter
pbi filter create Sales.Category --topn 5 --topn-by Facts.Revenue    # top N
pbi filter create Sales.OrderDate --mode relative --count 30 --unit Days  # relative date
pbi filter create Product.Name --mode advanced --operator contains --value "Pro"  # text filter
pbi filter create Product.Name --mode advanced --operator is-blank    # null check
pbi filter create Sales.Revenue --mode advanced --operator greater-than --value 1000

pbi filter delete Sales.Region                           # delete report filter
pbi filter delete Sales.Region --page "Overview"         # delete page filter
```

---

## Interactions

```bash
pbi interaction list "Overview"                              # list all interactions
pbi interaction set "Overview" slicer1 chart1 --mode NoFilter    # disable cross-filter
pbi interaction set "Overview" slicer1 chart1 --mode HighlightFilter
pbi interaction clear "Overview" slicer1                     # reset to defaults
```

---

## Styles, Components & Templates

**Styles** — reusable visual property sets:
```bash
pbi style create card-style background.color="#FFF" border.show=true border.radius=8
pbi style create card-style --from-visual "Overview" myCard   # capture from existing visual
pbi style list                                                # list available styles
pbi style apply "Overview" --style card-style                 # apply to all visuals on page
pbi style apply "Overview" myCard --style card-style          # apply to one visual

# In YAML, reference styles by name:
#   style: card-style
#   style: [base-card, dark-theme]    # multiple, applied in order
```

**Components** — reusable visual groups (stamps):
```bash
pbi component create "Overview" kpiGroup --name kpi-strip     # save group as component
pbi component apply "Detail" kpi-strip --x 16 --y 16         # stamp onto page
pbi component apply "Detail" kpi-strip --row 3 --gap 16      # stamp 3 copies in a row
pbi component apply "Detail" kpi-strip --set measure=Facts.Rev  # override parameters
```

**Page templates** — reusable page layouts:
```bash
pbi page template create "Overview" dashboard-layout          # save page as template
pbi page template apply "New Page" dashboard-layout           # apply to another page
pbi page template list
```

---

## Themes & Images

```bash
# Create theme from brand colors
pbi theme create "Corporate" --foreground=#333 --background=#FFF --accent=#0078D4 --font="Segoe UI"
pbi theme create "Brand" --accent=#E94560 --data-colors=#E94560,#0078D4,#1AAB40 --dry-run

# Inspect and edit active theme
pbi theme get                                # overview: palette, text classes, data colors
pbi theme get foreground                     # single property value
pbi theme get foreground background accent   # multiple properties
pbi theme get --raw                          # full JSON dump
pbi theme set foreground=#111111             # modify with cascade to derived colors
pbi theme set foreground=#111111 --no-cascade  # modify without cascade
pbi theme set dataColors=#0078D4,#E94560     # replace data color palette
pbi theme set textClasses.title.fontSize=14  # edit text class property
pbi theme properties                         # list all writable properties

# Save / load theme presets (project + global scope)
pbi theme save "corporate"                  # save active theme as project preset
pbi theme save "corporate" --global         # save as global preset (~/.config/pbi/themes/)
pbi theme load "corporate"                  # apply saved preset to project
pbi theme preset list                       # list saved presets (project + global)
pbi theme preset get "corporate"            # show preset as YAML
pbi theme preset delete "corporate" --force # delete a preset
pbi theme preset clone "corporate" --to-global   # clone project → global
pbi theme preset clone "corporate" --to-project  # clone global → project

# Visual style overrides (default formatting per visual type)
pbi theme style list                         # list types with style overrides
pbi theme style get columnChart              # show all overrides for a type
pbi theme style get * categoryAxis           # show specific object properties
pbi theme style get --raw                    # dump full visualStyles JSON
pbi theme style set columnChart legend.show=true legend.position=RightCenter
pbi theme style set * background.show=true background.transparency=0
pbi theme style set * filterCard.border[Applied]=true  # with $id selector
pbi theme style delete columnChart --force   # remove type overrides
pbi theme style delete * categoryAxis --force  # remove specific object

# Apply, export, delete, migrate
pbi theme apply corporate-theme.json        # apply custom theme from file
pbi theme export theme-backup.json          # export current theme
pbi theme delete --force                    # revert to base theme
pbi theme migrate old.json new.json --dry-run  # migrate color overrides to new theme

pbi image create logo.png                   # register image in project resources
pbi image list                              # list registered images
pbi image prune --force                     # remove unreferenced images
```

---

## Navigation & Bookmarks

```bash
# Set button/visual click actions
pbi nav page set "Overview" myButton "Detail View"          # navigate to page
pbi nav bookmark set "Overview" myButton "Show North"       # apply bookmark
pbi nav back set "Detail" backButton                        # navigate back
pbi nav url set "Overview" linkButton "https://example.com"
pbi nav drillthrough set "Overview" detailsBtn "Detail View"
pbi nav action get "Overview" myButton
pbi nav tooltip set "Overview" revenueChart "Card Tip"
pbi nav tooltip get "Overview" revenueChart
pbi nav tooltip clear "Overview" revenueChart
pbi nav action clear "Overview" myButton                    # remove action

# Bookmarks
pbi bookmark create "Show North" "Overview" --hide chart2 chart3
pbi bookmark list
```

---

## Project Overview & Validation

```bash
pbi map                          # full project map as YAML (pages, visuals, model)
pbi map --pages                  # pages and visuals only
pbi map --model                  # model only
pbi map --page "Overview"       # single page detail
pbi info                         # quick project summary
pbi validate                    # check for structural errors, schema violations, and warnings
pbi render "Overview" -o page.html   # HTML mockup of page layout
pbi capabilities                 # show what the CLI supports vs PBIR spec
```

`pbi validate` checks JSON structure, page order, visual interactions, bookmarks, layout issues (overlaps, out-of-bounds), relationship gaps, and validates visual objects/properties against the PBI Desktop schema.
