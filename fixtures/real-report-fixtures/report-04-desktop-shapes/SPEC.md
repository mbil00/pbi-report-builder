# Report Fixture Spec 04: Desktop Shapes

## Purpose

This fixture is a **ground-truth sample of what Power BI Desktop writes**. It is built by hand in Desktop and committed exactly as Desktop saved it. Its job is to give the CLI's new write paths a canonical sample to be derived from and tested against, as the engineering rule in `CLAUDE.md` requires:

> New write paths must be validated against the extracted PBI Desktop schema or derived from a canonical exported PBIR sample with test coverage. No guessing JSON structures.

Several open issues are blocked because the repo has no Desktop-made sample of the shape they need (textbox runs, `///` descriptions, one-sided cardinality, per-value data colours, slicer sync groups and saved selections). Fixtures 01 to 03 don't fill that gap:

- They were partly written or edited by the CLI. For example, the `01-kitchen-sink` header textbox stores its run as `"value": "'Regional Performance'"` and `"fontSize": "'20pt'"`, the CLI's DAX-literal form that issue #34 reports as a bug, so it can't serve as the reference for fixing #34.
- Their visuals carry CLI-assigned names (`qaChart`, `card-variance`), not the random IDs Desktop assigns.
- None of them contains a slicer sync group, a `///` description, a many-to-many or one-to-one relationship, a `dataPoint` colour selector, or a theme with Desktop-written text classes.

`BUILD-CHECKLIST.md` has the click-by-click build steps, with all DAX and values. This document says **what** the fixture contains and **why**.

## Build Constraints

- Built only in Power BI Desktop: no `pbi` writes, no hand edits, no external tools (Tabular Editor and similar). Anything the CLI or a person wrote would defeat the purpose.
- Saved as PBIP with the PBIR report format and TMDL semantic model.
- Import mode only; sources are the local CSVs in `data/`, plus one Enter-data table.
- Auto date/time and relationship autodetection are off, so every table and relationship in the model was created on purpose.
- Committed as written, except `.pbi/cache.abf` and `.pbi/localSettings.json`, which Desktop's own `.gitignore` excludes (fixtures 01 to 03 committed them; they are machine-local and not under test).
- `BUILD-NOTES.md` (filled in by the builder) records the Desktop version, resource file names, skipped steps and deviations.
- Small data (about 3,800 rows in total) so the fixture stays light; volume isn't under test.

## Domain

Project delivery: projects grouped into portfolios, tasks with a workflow status, people in teams, time and expense entries, task tags (many-to-many through a bridge), QA notes (one per project) and portfolio targets.

## Data Model

### Import tables

| Table | Source CSV | Rows | Grain and notable columns |
|---|---|---|---|
| `Date` | `Date.csv` | 731 | One row per day, 2024-01-01 to 2025-12-31. Marked as date table. `MonthName` sorts by `MonthNumber`. |
| `Project` | `Project.csv` | 12 | One row per project. `Portfolio` (4 values, non-unique), `Priority` sorted by `PriorityRank` (source column), `Budget` decimal, `IsActive` boolean. |
| `Person` | `Person.csv` | 16 | One row per person. `Team`, `Role`, `Country` (data category Country/Region). |
| `Rates (EUR)` | `RatesEUR.csv` | 6 | One row per role. `HourlyRate` decimal. |
| `Task` | `Task.csv` | 600 | One row per task (fact). `Status` sorted by `StatusRank`, three dates (`CompletedDate` blank unless completed), decimal hours, integer story points. |
| `Tag` | `Tag.csv` | 8 | One row per tag. |
| `TaskTag` | `TaskTag.csv` | 905 | Bridge: task-to-tag pairs, 0 to 3 tags per task. |
| `Time & Expenses` | `TimeAndExpenses.csv` | 1,500 | One row per time or expense entry (fact). `Amount` is a **Fixed decimal number** (currency type); `IsBillable` boolean. |
| `Q/A Notes` | `QANotes.csv` | 12 | Exactly one row per project. |
| `Portfolio Target` | `PortfolioTarget.csv` | 8 | One row per portfolio and year; `Portfolio` is non-unique. |

CSV file names are plain; the special-character table names are applied in Desktop, so the fixture captures how Desktop names, quotes and escapes them.

### Other tables

- `Measures Table`: created with **Enter data**; one hidden placeholder column (Desktop named it `Column`); holds most measures.
- Nine calculated tables, one per DAX table form (see the coverage table, #40).
- `Metric Selector`: a field parameter created through **Modeling > New parameter > Fields**.

### Relationships

| # | From | To | Cardinality | Cross filter | Active | Why |
|---|---|---|---|---|---|---|
| R1 | `Task[CreatedDate]` | `Date[Date]` | *:1 | Single | yes | Baseline |
| R2 | `Task[DueDate]` | `Date[Date]` | *:1 | Single | **no** | Inactive relationship; used by `USERELATIONSHIP` |
| R3 | `Time & Expenses[EntryDate]` | `Date[Date]` | *:1 | Single | yes | Special-character table in a relationship |
| R4 | `Task[ProjectKey]` | `Project[ProjectKey]` | *:1 | Single | yes | |
| R5 | `Task[PersonKey]` | `Person[PersonKey]` | *:1 | Single | yes | |
| R6 | `Time & Expenses[ProjectKey]` | `Project[ProjectKey]` | *:1 | Single | yes | |
| R7 | `Time & Expenses[PersonKey]` | `Person[PersonKey]` | *:1 | Single | yes | |
| R8 | `Person[Role]` | `Rates (EUR)[Role]` | *:1 | Single | yes | Text key; parenthesised table name |
| R9 | `TaskTag[TaskKey]` | `Task[TaskKey]` | *:1 | **Both** | yes | Bidirectional bridge |
| R10 | `TaskTag[TagKey]` | `Tag[TagKey]` | *:1 | Single | yes | |
| R11 | `Q/A Notes[ProjectKey]` | `Project[ProjectKey]` | **1:1** | Both | yes | One-to-one |
| R12 | `Portfolio Target[Portfolio]` | `Project[Portfolio]` | **\*:\*** | Single (Project filters Portfolio Target) | yes | Many-to-many |

The relationship set is free of ambiguous paths: `Date`, `Project` and `Person` filter both facts directly, and the bidirectional and one-to-one relationships only connect leaf tables.

## Coverage By Issue

Each row says what the fixture holds for the issue, where to find it, and what the Desktop output should settle.

### Blocked issues (no Desktop sample in the repo today)

| Issue | Fixture content | Where | What it settles |
|---|---|---|---|
| #34 Textbox literals | Text box with 2 paragraphs and 3 runs: font family (Georgia), size, colour, bold, italic. A second text box with a plain run plus a hyperlink run. A third, unformatted text box for comparison. | `Overview`: `Overview Header`, `Overview Link`; `QA Hidden`: `QA Note` | The exact `paragraphs` / `textRuns` / `textStyle` shape and value encoding (plain strings vs literals, `fontSize` units, colour form), the hyperlink `url` field, and what an unstyled run omits. |
| #38 Descriptions | `///` descriptions on a table (`Task`), a column (`Task[Status]`), measures (`Task Count` two lines, `Completed Tasks` with quotes and `&`, `Open Tasks`) and a hierarchy (`Date[Calendar]`). | TMDL: `Task`, `Measures Table`, `Date` | Placement of `///` for each object kind, multi-line form, escaping of quotes. Adjacent described measures also give #56 (descriptions of neighbours on delete) a real sample. |
| #46 Cardinality | R11 one-to-one, R12 many-to-many, R9 bidirectional, R2 inactive. | `relationships.tmdl` | Which of `fromCardinality` / `toCardinality` / `crossFilteringBehavior` / `isActive` Desktop writes and omits for each kind. |
| #41 Data colours | Stacked column with a fixed colour per legend value (text); clustered column with a colour per measure series; bar chart with "Show all" colours per category (text); donut with colours per boolean value; column chart coloured per integer category value (`13`). | `Overview`: `Tasks by Status`; `Chart Gallery`: `Hours by Measure Series`, `Hours by Team`, `Billable Split`, `Tasks per Story Points` | `dataPoint` selector shapes (`scopeId` comparisons vs `metadata` series selectors) and literal typing per data type: text `'...'`, boolean `true`, integer `13L`. |
| #42 Slicers | Portfolio slicer in sync group `PortfolioSync` on two pages, plus a hidden synced copy on a third; saved single selection; saved multi selection; inverted "all except" selection; date range ("Between") selection. | `Overview`, `Task Board`, `Chart Gallery` | `syncGroup` (`groupName`, `fieldChanges`, `filterChanges`), how a hidden synced slicer is stored, and the saved-selection `filter` shapes, including the inverted form and the date range. |

### Related issues (more Desktop data improves the tests)

| Issue | Fixture content | Where | What it settles |
|---|---|---|---|
| #35 Measure filter literals | Visual-level filters: integer-format measure `>= 1`; decimal-format measure `> 1.5`; measure with no format string, integer (`>= 10`) and decimal (`>= 0.95`); currency measure over a Fixed decimal column (`> 500`); percent measure (`> 0.5`); numeric column (`>= 3`) for comparison; Top N; relative date. Page-level boolean filter. | `Filter Lab` | Literal suffix per type (`L`, `D`, `M` or other) for measures vs columns, Top N and relative-date filter JSON. |
| #40 Calculated table columns | `SELECTCOLUMNS`, `ROW`, `ADDCOLUMNS` over `VALUES`, `SUMMARIZE`, `SUMMARIZECOLUMNS`, `GENERATESERIES` with integers, a `{ }` row constructor, `UNION`, `DATATABLE`. | Tables `Project List`, `Owner's Info`, `Status Summary`, `Portfolio Status`, `Portfolio Hours`, `Hours Band`, `Priority Levels`, `Milestone Dates`, `Status Colors` | The `column` blocks Desktop writes per form: names (`Value`, `Value1`, `[Status]`, ...), `dataType`, `sourceColumn`, `isDataTypeInferred`, `lineageTag`. Three of them are bound in visuals on `QA Hidden`. |
| #45 Measures-only table | `Measures Table` from Enter data with a hidden placeholder column; measures also in the facts `Task` and `Time & Expenses`. | TMDL; every page | A realistic measures table to test the relationship-path warning against. |
| #52 TMDL naming | Table names `Rates (EUR)`, `Time & Expenses`, `Q/A Notes`, `Owner's Info`, `Measures Table`, `Portfolio Target`. Ten CSV queries loaded in a fixed order. | `definition/tables/`, `model.tmdl` | Desktop's file naming and escaping (notably `/` and `'`), TMDL quoting, line endings, `ref table` order, `PBI_QueryOrder`. |
| #29 Resource names | Theme imported from `Desktop Shapes Theme.json` and image inserted from `Team Logo.png` (both with spaces). | `StaticResources/RegisteredResources/`, `report.json` | The resource file names and `report.json` references Desktop produces; `BUILD-NOTES.md` records names before and after theme customization. |
| #33 / #54 Multi-tile card | New card (`cardVisual`) with 4 measures, per-series accent bar, value font size and label colour, a callout-area setting if the build has one, a reference label, and a visual-wide background. Three plainer cards for contrast. | `Overview`: `Delivery KPIs`; `Project Detail`: `Project KPIs`, `Portfolio Target`; `Person Tooltip`: `Tooltip KPIs` | Which properties Desktop writes with a per-measure selector vs visual-wide, and the reference-label shape. |
| #49 Theme text classes | Theme without `textClasses`, then Text set through **Customize current theme** (General, Title, Cards and KPIs, Tab headers). | Theme resource | Which `textClasses` keys and colour forms Desktop writes. |
| #55 Rename bindings | A second copy of the project in which measure `Total Hours` is renamed to `Hours Logged` and column `Person[PersonName]` to `Person Name`. Both are bound in projections, sort, Top N filter, conditional formatting (data bars), a tooltip page field, measure DAX and a field parameter. | `report-04-desktop-shapes-renamed/` | Exactly what Desktop rewrites on rename: `queryRef`, `nativeQueryRef`, display names, filters, sort, CF, DAX, field parameter. A diff of the two folders is the reference for the CLI cascade. |
| #31 Sort by column | `Project[Priority]` sorted by source column `PriorityRank`; `Task[Status]` by `StatusRank`; `Date[MonthName]` by `MonthNumber`; calculated `Task[Duration Band]` sorted by calculated `Duration Band Order`, both derived from `Duration Days` (valid, no loop). | TMDL | Valid sort-by baselines, including a calculated-column chain the loop check must not flag. Also a Desktop sample for #36 (sortByColumn on calculated columns). |

### Extras (cheap, broaden the sample)

| Area | Fixture content |
|---|---|
| Conditional formatting | `Portfolio Matrix`: background rules, font colour by field value (`Status Color` measure), font colour gradient with a middle stop. `People Hours`: data bars. |
| Matrix | Hierarchy rows (`Portfolio Tree`), column field, row subtotals at the bottom with a custom label, column subtotals, expanded one level. |
| Drillthrough | `Project Detail` on `Project[ProjectName]`, keep all filters, auto back button. |
| Tooltip page | `Person Tooltip`, tooltip canvas, tooltip field, hidden; used by `Filter - Top N`. |
| Hidden page | `QA Hidden`. |
| Bookmarks | Two bookmarks in group `Task Board Views` (data state), one display-only bookmark (`Overview - Hide Logo`), bookmark navigator. |
| Navigation | Page navigator, bookmark navigator, drillthrough back button. |
| Field parameter | `Metric Selector` with three measures, its auto-created slicer and a chart bound to it. |
| Hierarchies | `Date[Calendar]` (with description), `Project[Portfolio Tree]` (used in the matrix). |
| Date table | `Date` marked as date table; auto date/time off. |
| Format strings | Whole number with separator, 1 and 2 decimals, percent, currency (EUR), custom (`"€"#,0.00" /h"`), date column format, and three measures left without a chosen format (Desktop inferred `0` for `Story Points`, so two have no format string). |
| Display folders | Measures in `Counts`, `Counts\Status` (nested), `Hours`, `Money`, `Ratios`, `Formatting`; columns in `Effort`, `Duration`. |
| Column metadata | Summarize-by (none, average), data category, hidden keys. |
| Chart types | Stacked column, clustered column, clustered bar, line, donut, line and clustered column, matrix, table, slicers, cards, text boxes, image, buttons; optional scatter, treemap, shape. |

## Pages

Page order and names are part of the contract. Visuals are identified by **title text** (see "Consuming The Fixture").

| # | Page | Kind | Visuals (title text) |
|---|---|---|---|
| 1 | `Overview` | normal | `Overview Header`, `Overview Link`, `Team Logo Image`, `Delivery KPIs`, `Tasks by Status`, `Portfolio Slicer`, `Page Navigator` |
| 2 | `Task Board` | normal | `Portfolio Slicer`, `Priority Slicer`, `Status Slicer`, `Team Slicer`, `Date Range Slicer`, `Portfolio Matrix`, `People Hours`, `Task Board Views Navigator` |
| 3 | `Filter Lab` | normal, page filter | `Filter - Integer Measure`, `Filter - Decimal Measure`, `Filter - No Format Integer`, `Filter - No Format Decimal`, `Filter - Currency Measure`, `Filter - Percent Measure`, `Filter - Numeric Column`, `Filter - Top N`, `Filter - Relative Date` |
| 4 | `Chart Gallery` | normal | `Hours by Measure Series`, `Hours by Team`, `Billable Split`, `Tasks per Story Points`, `Hours Trend`, hidden synced `Portfolio Slicer`; optional `Hours vs Tasks`, `Hours Treemap` |
| 5 | `Project Detail` | drillthrough | `Back Button`, `Project KPIs`, `Project Tasks`, `Tags on Project`, `Q/A Review`, `Portfolio Target` |
| 6 | `Person Tooltip` | tooltip, hidden | `Tooltip KPIs`, `Tooltip Status Mix` |
| 7 | `QA Hidden` | hidden | `Metric Selector Slicer`, `Metric by Portfolio`, `QA Note`, `Status Colors Table`, `Owner Info Table`, `Rates Table`; optional `QA Frame` |

About 45 visuals in total. Saved slicer state on `Task Board`: Priority `High`; Status `In progress` + `Blocked`; Team all except `Design`; Date 2024-03-01 to 2025-06-30; Portfolio none.

## Consuming The Fixture

- **Find visuals by title text**, never by visual name: Desktop assigns random 20-character IDs. Every visual has a unique title text per page; on text boxes, images, buttons and slicers the title is switched off but the text is still saved.
- Don't assert on positions, z-order, IDs, lineage tags or the Desktop version strings; they're incidental.
- Assert on shapes: the property structure, literal encodings and which keys are present or absent. That is what the fixture is for.
- `tests/test_desktop_shapes_fixture.py` checks that the build inputs regenerate byte-identically. The fixture harness (`tests/test_fixture_harness.py`) runs the CLI over the Desktop output, and tests such as `test_desktop_literal_writes.py`, `test_data_colors.py` and `test_slicer_state.py` compare CLI writes with it. `test_theme_read_commands.py` checks what the theme commands print for its theme.
- When Desktop's output disagrees with an issue's description, the fixture wins: record that on the issue.

## Rename Snapshot (#55)

`report-04-desktop-shapes-renamed/` holds a copy of the saved project with exactly two renames done in Desktop: measure `Total Hours` to `Hours Logged`, and column `Person[PersonName]` to `Person Name`. Diffing the two folders shows every file Desktop rewrites on a rename. The copy holds only the PBIP artifacts (`.pbip`, `.Report`, `.SemanticModel`, `.gitignore`), not `data/` or the docs.

## Acceptance Checklist

- PBIR (`definition/pages/`) and TMDL (`definition/tables/`), no `model.bim`.
- 7 pages in the order above; `Person Tooltip` and `QA Hidden` hidden; `Project Detail` is a drillthrough target; `Person Tooltip` is a tooltip page.
- 21 tables: 10 imported, `Measures Table`, 9 calculated, `Metric Selector`.
- 12 relationships, including one 1:1, one many-to-many, one bidirectional and one inactive.
- At least 7 `///` description lines, including one two-line description.
- 3 slicers carrying `syncGroup`; saved slicer selections as listed above.
- 4 `cardVisual` visuals; `Delivery KPIs` has per-series formatting.
- 3 bookmarks (two in group `Task Board Views`).
- Theme and image registered as resources; their file names recorded in `BUILD-NOTES.md`.
- No `*:Zone.Identifier`, `cache.abf` or `localSettings.json` files committed.
- `BUILD-NOTES.md` filled in.
- Optional: `report-04-desktop-shapes-renamed/` committed alongside.

## What The Build Showed

Built with Power BI Desktop 2.159.1231.0 (October 2026); see `BUILD-NOTES.md`. These are the shapes Desktop wrote. Where an issue's description disagrees, the fixture wins.

| Issue | What Desktop wrote |
|---|---|
| #34 Textbox | Run `value` is a plain string. `textStyle` holds plain strings: `fontSize: "24pt"`, `color: "#1f3a5f"` (lowercase hex), `fontWeight: "bold"`, `fontStyle: "italic"`, `fontFamily` only when it isn't the default. A hyperlink run has `url` and an empty `textStyle: {}`; an unformatted run has only `value`. |
| #38 Descriptions | One `///` line per description line, directly above the object (`table`, `column`, `measure`, `hierarchy`), quotes and `&` unescaped. The Properties pane accepted a pasted two-line description. |
| #46 Cardinality | Only non-defaults are written: `isActive: false`, `crossFilteringBehavior: bothDirections`, 1:1 as `fromCardinality: one`, \*:\* as `toCardinality: many`. |
| #41 Data colours | `dataPoint` with `selector.data[].scopeId` = `Comparison` (`ComparisonKind: 0`) against a literal: text `'Completed'`, boolean `true`/`false`, integer `13L`. A measure series uses `selector.metadata: "Measures Table.Estimate Hours"`. Colours are quoted uppercase hex (`'#20A741'`). No entry is written when the colour equals the theme default for that slot, and "Show all" isn't persisted. |
| #42 Slicers | Each synced slicer carries `syncGroup: {groupName, fieldChanges, filterChanges}`; the hidden copy is an ordinary slicer with `isHidden: true`. Saved selections live in `objects.general[0].properties.filter.filter` (a Version 2 query): `In` for single and multi; `Not(In)` plus `data.isInvertedSelectionMode: true` for "all except"; a date range is `>= start` `And` `< end + 1 day`, with `data.startDate`/`endDate`/`mode: 'Between'`. Single select is `selection.strictSingleSelect: true`. |
| #35 Filter literals | Measure filters are `Advanced` with a `Comparison`: integer-format `1L`, decimal-format `1.5D`, no-format integer `10L`, no-format decimal `0.95D`, currency (Fixed decimal) `500M`, percent `0.5D`; numeric column `3L`. Top N is `In` over a `subquery` source; relative date is `Between` over `DateSpan`/`DateAdd` of `Now`. |
| #40 Calculated tables | `GENERATESERIES` gives `Value`; a `{ }` constructor gives `Value1`, `Value2`; `VALUES`/`SUMMARIZE` columns keep the source name with `sourceColumn: Task[Status]`; named columns use `sourceColumn: [Name]`. Enter data is now a calculated partition: `Row("Column", BLANK())`. |
| #52 TMDL naming | `Q/A Notes` is stored as `Q%2FA Notes.tmdl`; `Owner's Info.tmdl` keeps the apostrophe in the file name and is `'Owner''s Info'` inside. CRLF line endings. `PBI_QueryOrder` follows load order; `ref table` lists imported tables, then created ones, in creation order. |
| #29 Resources | Spaces become `_` and a numeric suffix is appended: `Team_Logo9246818840412365.png`. Customizing the theme replaced the file with a new suffix. The image visual keeps the original name in `image.name` (`'Team Logo.png'`) and `fit: 'Fit'`. |
| #33 / #54 Card | Per-series formatting uses `selector.metadata`, visual-wide uses `selector.id: "default"`; `value.fontSize` is `28D`. The reference label is a `referenceLabel` entry whose selector combines a `dataViewWildcard`, the series `metadata`, an `id` and an `order`, plus `referenceLabelLayout`. The card background ended up in `cardCalloutArea` with the default selector. |
| #49 Theme | `textClasses` keys `label`, `title`, `callout`, `header`; `fontFace` only where the font changed (as a full font stack). |
| #55 Rename | Desktop rewrites every field expression's `Property`, the DAX references, the field parameter's `NAMEOF` (its label stays `"Total Hours"`), the linguistic metadata and one `nativeQueryRef`. It leaves `queryRef`, the other `nativeQueryRef`s, `displayName` and the card's `selector.metadata` with the old name. Renaming a column adds a `Table.RenameColumns` step to the M query and changes `sourceColumn`. |

Other observations:

- New pages default to 1920 × 1080.
- Desktop writes `options.preserveNewVisualVisibility` into bookmarks and then warns on reopen that its own schema doesn't allow it.
- Renaming a slicer sync group after pages are synced moves only the selected slicer and adds new copies to the other pages (the checklist now warns about it).

## Known Uncertainties (Resolved)

All resolved by this build: `/` and `'` were accepted in table names; the Properties pane accepted a two-line description; the new card has a callout area; PBIP, TMDL and PBIR are standard (no preview toggles); `PBI_QueryOrder` follows load order.
