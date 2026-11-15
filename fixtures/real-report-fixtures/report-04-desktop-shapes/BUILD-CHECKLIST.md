# Build Checklist: Report 04 Desktop Shapes

## Goal

Build a PBIP fixture **entirely by hand in Power BI Desktop**, so the repo gets ground-truth samples of the JSON (PBIR) and TMDL shapes Desktop writes. `SPEC.md` explains what each item is for and which GitHub issue it unblocks.

Ground rules:

- Use only Power BI Desktop. Don't run any `pbi` command that writes to this project, don't edit files by hand, and don't use external tools (Tabular Editor and similar).
- Type names, DAX and values exactly as written here. Text in `code` is meant to be pasted.
- If a step is impossible in your Desktop build, skip it and note the step number in `BUILD-NOTES.md` (template in step 17). Don't improvise a workaround.
- Steps marked **(optional)** can be skipped when time is short; they are extras, not issue blockers.
- Save often (Ctrl+S). Saving doesn't affect the result.

Estimated time: about 60 minutes for the required steps, plus about 15 minutes for the optional ones and the rename snapshot (step 16).

Dataset location (in the repo):

- `fixtures/real-report-fixtures/report-04-desktop-shapes/data`

Other inputs in the same folder:

- `Desktop Shapes Theme.json` (custom theme; the space in the file name is deliberate)
- `Team Logo.png` (image; the space in the file name is deliberate)

## 1. Before You Start

1. Build on Windows from a Windows-side clone of the repo (the earlier fixtures used `C:\WSL\pbi-report-builder\`). The CSV paths Desktop records in the model will point there; that's expected.
2. If you must build directly on a WSL path (`\\wsl.localhost\...`), expect Windows to create `*:Zone.Identifier` files next to everything you copy; step 15 removes them.
3. Open Power BI Desktop. Record the version from **Help > About** for `BUILD-NOTES.md`.
4. **File > Options and settings > Options > Preview features**: tick each of these that is listed (on newer builds some are already standard and not listed, which is fine):
   - `Power BI Project (.pbip) save option`
   - `Store semantic model using TMDL format`
   - `Store reports using enhanced metadata format (PBIR)`
5. Restart Desktop if it asks, then start a new blank report.
6. **Options > Current file > Data Load**:
   - Time intelligence: untick `Auto date/time`.
   - Relationships: untick `Import relationships from data sources on first load`, `Update or delete relationships when refreshing data` and `Autodetect new relationships after data is loaded`.
7. **Options > Current file > Regional settings**: `Locale for import` = `English (United States)`.
8. **File > Save as**: browse to `fixtures\real-report-fixtures\report-04-desktop-shapes\`, file name `04-desktop-shapes`, type `Power BI project files (*.pbip)`. Save.
9. Check in Explorer that the folder now has `04-desktop-shapes.pbip`, `04-desktop-shapes.Report\definition\` and `04-desktop-shapes.SemanticModel\definition\` (a `definition` folder, not a `model.bim` file). If you see `model.bim` or a single `report.json` at the root of `.Report`, the TMDL/PBIR options aren't active: fix step 4 and save again.

## 2. Load The CSVs

Load the files **one at a time, in this order** (Desktop may record the load order in `PBI_QueryOrder`; the fixed order keeps it reproducible):

| Load # | CSV file | Rename table to | Rows |
|---|---|---|---|
| 1 | `Date.csv` | `Date` | 731 |
| 2 | `Project.csv` | `Project` | 12 |
| 3 | `Person.csv` | `Person` | 16 |
| 4 | `RatesEUR.csv` | `Rates (EUR)` | 6 |
| 5 | `Task.csv` | `Task` | 600 |
| 6 | `Tag.csv` | `Tag` | 8 |
| 7 | `TaskTag.csv` | `TaskTag` | 905 |
| 8 | `TimeAndExpenses.csv` | `Time & Expenses` | 1500 |
| 9 | `QANotes.csv` | `Q/A Notes` | 12 |
| 10 | `PortfolioTarget.csv` | `Portfolio Target` | 8 |

For each row:

1. **Home > Get data > Text/CSV**, pick the file, click **Load** (not Transform Data).
2. In the **Data** pane, right-click the new table > **Rename**, and type the name from the "Rename table to" column exactly, including spaces and punctuation (`Rates (EUR)`, `Time & Expenses`, `Q/A Notes`).
3. If Desktop refuses a name (most likely `Q/A Notes`), use `QA Notes` instead and record it in `BUILD-NOTES.md`. Don't try other variants.

## 3. Fix Column Types In Power Query

**Home > Transform data**. For each query below, check the type icon in each column header and change it where it differs (click the icon > pick the type > **Replace current** if asked). Then **Home > Close & Apply**.

| Table | Column | Type |
|---|---|---|
| Date | Date | Date |
| Date | Year, MonthNumber | Whole number |
| Date | IsWeekend | True/False |
| Project | ProjectKey, PriorityRank | Whole number |
| Project | StartDate | Date |
| Project | Budget | Decimal number |
| Project | IsActive | True/False |
| Person | PersonKey | Whole number |
| Person | StartDate | Date |
| Rates (EUR) | HourlyRate, OvertimeMultiplier | Decimal number |
| Task | TaskKey, ProjectKey, PersonKey, StatusRank, StoryPoints | Whole number |
| Task | CreatedDate, DueDate, CompletedDate | Date |
| Task | EstimateHours, ActualHours | Decimal number |
| Tag | TagKey | Whole number |
| TaskTag | TaskKey, TagKey | Whole number |
| Time & Expenses | EntryKey, ProjectKey, PersonKey | Whole number |
| Time & Expenses | EntryDate | Date |
| Time & Expenses | Hours | Decimal number |
| Time & Expenses | **Amount** | **Fixed decimal number** (the `$ 1.2` currency type, not "Decimal number") |
| Time & Expenses | IsBillable | True/False |
| Q/A Notes | ProjectKey, QAScore | Whole number |
| Q/A Notes | ReviewDate | Date |
| Portfolio Target | Year, TargetHours | Whole number |
| Portfolio Target | TargetBudget | Decimal number |

All other columns stay Text. `Task[CompletedDate]` is blank for unfinished tasks; that's expected.

## 4. Measures Table (Enter Data)

1. **Home > Enter data**.
2. Leave the grid as it is (one column, no values typed). Current builds name it `Column`; older ones `Column1`.
3. Name: `Measures Table`. Click **Load**.
4. In the Data pane, right-click that placeholder column > **Hide in report view**. Keep the column; don't delete it.

## 5. Relationships

Open **Modeling > Manage relationships > New** for each row. "From" is the first table in the dialog, "To" the second. Leave everything not listed at its default.

| # | From (table[column]) | To (table[column]) | Cardinality | Cross filter direction | Active |
|---|---|---|---|---|---|
| R1 | `Task[CreatedDate]` | `Date[Date]` | Many to one (*:1) | Single | yes |
| R2 | `Task[DueDate]` | `Date[Date]` | Many to one (*:1) | Single | **no** (untick "Make this relationship active") |
| R3 | `Time & Expenses[EntryDate]` | `Date[Date]` | Many to one (*:1) | Single | yes |
| R4 | `Task[ProjectKey]` | `Project[ProjectKey]` | Many to one (*:1) | Single | yes |
| R5 | `Task[PersonKey]` | `Person[PersonKey]` | Many to one (*:1) | Single | yes |
| R6 | `Time & Expenses[ProjectKey]` | `Project[ProjectKey]` | Many to one (*:1) | Single | yes |
| R7 | `Time & Expenses[PersonKey]` | `Person[PersonKey]` | Many to one (*:1) | Single | yes |
| R8 | `Person[Role]` | `Rates (EUR)[Role]` | Many to one (*:1) | Single | yes |
| R9 | `TaskTag[TaskKey]` | `Task[TaskKey]` | Many to one (*:1) | **Both** | yes |
| R10 | `TaskTag[TagKey]` | `Tag[TagKey]` | Many to one (*:1) | Single | yes |
| R11 | `Q/A Notes[ProjectKey]` | `Project[ProjectKey]` | **One to one (1:1)** | Both (Desktop forces it) | yes |
| R12 | `Portfolio Target[Portfolio]` | `Project[Portfolio]` | **Many to many (\*:\*)** | Single: **`Project` filters `Portfolio Target`** | yes |

Notes:

- R9 may show a warning about bidirectional filtering. Accept it. If Desktop refuses "Both" because of ambiguity, keep Single and record it.
- R12 shows a many-to-many warning. Accept it. Pick the cross-filter option in which `Project` filters `Portfolio Target`.
- Close the dialog and check in Model view that there are 12 relationships and R2 is drawn dashed (inactive).

## 6. Calculated Columns

Select the table in the Data pane, then **Table tools > New column**, paste the DAX, press Enter.

Table `Task`:

```dax
Duration Days = DATEDIFF ( Task[CreatedDate], Task[DueDate], DAY )
```

```dax
Duration Band = SWITCH ( TRUE (), Task[Duration Days] <= 7, "Up to 1 week", Task[Duration Days] <= 14, "1-2 weeks", Task[Duration Days] <= 30, "2-4 weeks", "Over 4 weeks" )
```

```dax
Duration Band Order = SWITCH ( TRUE (), Task[Duration Days] <= 7, 1, Task[Duration Days] <= 14, 2, Task[Duration Days] <= 30, 3, 4 )
```

Table `Project`:

```dax
Project Label = Project[ProjectCode] & " - " & Project[ProjectName]
```

Table `Person`:

```dax
Hourly Rate = RELATED ( 'Rates (EUR)'[HourlyRate] )
```

## 7. Column Properties

Do these in Report view (Data pane + **Column tools** ribbon) or Model view (Properties pane), whichever is quicker.

### 7a. Sort by column

Select the first column, then **Column tools > Sort by column** > pick the second.

| Column | Sort by |
|---|---|
| `Date[MonthName]` | `MonthNumber` |
| `Project[Priority]` | `PriorityRank` |
| `Task[Status]` | `StatusRank` |
| `Task[Duration Band]` | `Duration Band Order` |

### 7b. Hide in report view

Right-click > **Hide in report view** for:

- `Date[MonthNumber]`
- `Project[ProjectKey]`, `Project[PriorityRank]`
- `Person[PersonKey]`
- `Task[TaskKey]`, `Task[ProjectKey]`, `Task[PersonKey]`, `Task[StatusRank]`, `Task[Duration Band Order]`
- `Tag[TagKey]`
- `TaskTag[TaskKey]`, `TaskTag[TagKey]`
- `Time & Expenses[EntryKey]`, `Time & Expenses[ProjectKey]`, `Time & Expenses[PersonKey]`
- `Q/A Notes[ProjectKey]`
- (The `Measures Table` placeholder column is already hidden from step 4.)

### 7c. Formats, summarization, data category, display folders

| Column | Setting | Value |
|---|---|---|
| `Task[CreatedDate]` | Format | `2001-03-14 (yyyy-MM-dd)` |
| `Project[Budget]` | Format | Currency, symbol `€ Euro (€ 123)`, 0 decimal places |
| `Rates (EUR)[HourlyRate]` | Format | Decimal number, 2 decimal places |
| `Project[PriorityRank]` | Summarization | Don't summarize |
| `Q/A Notes[QAScore]` | Summarization | Average |
| `Person[Country]` | Data category | Country/Region |
| `Task[EstimateHours]`, `Task[ActualHours]` | Display folder (Model view > Properties) | `Effort` |
| `Task[Duration Days]`, `Task[Duration Band]` | Display folder | `Duration` |

## 8. Mark The Date Table And Create Hierarchies

1. Select table `Date` > **Table tools > Mark as date table** > date column `Date` > OK.
2. Model view: right-click `Date[Year]` > **Create hierarchy**. In the Properties pane, rename the hierarchy to `Calendar`, and in its level list select `Year`, `Quarter`, `MonthName`, `Date` in that order, then **Apply Level Changes**.
3. Same for `Project[Portfolio]`: hierarchy name `Portfolio Tree`, levels `Portfolio`, `ProjectName`.

## 9. Calculated Tables

**Modeling > New table**, paste, press Enter. Don't rename any generated column.

```dax
Project List = SELECTCOLUMNS ( Project, "Code", Project[ProjectCode], "Name", Project[ProjectName], "Budget EUR", Project[Budget], "Start", Project[StartDate] )
```

```dax
Owners Info = ROW ( "Owner", "Fixture Team", "Version", 4, "Released", DATE ( 2026, 1, 15 ), "Coverage", 0.85, "Is Synthetic", TRUE () )
```

After creating `Owners Info`, rename the **table** in the Data pane to `Owner's Info` (with an apostrophe). If Desktop refuses, keep `Owners Info` and record it.

```dax
Status Summary = ADDCOLUMNS ( VALUES ( Task[Status] ), "Tasks", CALCULATE ( COUNTROWS ( Task ) ), "Hours", CALCULATE ( SUM ( Task[ActualHours] ) ) )
```

```dax
Portfolio Status = SUMMARIZE ( Task, Project[Portfolio], Task[Status] )
```

```dax
Portfolio Hours = SUMMARIZECOLUMNS ( Project[Portfolio], "Hours Sum", SUM ( 'Time & Expenses'[Hours] ) )
```

```dax
Hours Band = GENERATESERIES ( 0, 40, 8 )
```

```dax
Priority Levels = { ( "Low", 1 ), ( "Medium", 2 ), ( "High", 3 ), ( "Critical", 4 ) }
```

```dax
Milestone Dates = UNION ( SELECTCOLUMNS ( Task, "Date", Task[CreatedDate], "Kind", "Created" ), SELECTCOLUMNS ( Task, "Date", Task[DueDate], "Kind", "Due" ) )
```

```dax
Status Colors = DATATABLE ( "Status", STRING, "Hex", STRING, "Sort", INTEGER, { { "Not started", "#A0A0A0", 1 }, { "In progress", "#F2A900", 2 }, { "Blocked", "#D64550", 3 }, { "Completed", "#20A741", 4 } } )
```

## 10. Measures

Select the home table in the Data pane, **Home > New measure**, paste, press Enter. Then set the format in the **Measure tools** ribbon and the display folder in Model view > Properties (a `\` in a folder name makes a subfolder).

"Untouched" means: don't open the format dropdown for that measure at all. Those measures exist to capture what Desktop writes when no format string is chosen. Desktop still infers one for a plain `SUM` over a whole-number column (`Story Points` gets `0`); that's expected.

### Home table `Measures Table`

| # | DAX | Format | Display folder |
|---|---|---|---|
| M1 | `Task Count = COUNTROWS ( Task )` | Whole number, thousands separator on | `Counts` |
| M2 | `Completed Tasks = CALCULATE ( [Task Count], Task[Status] = "Completed" )` | Whole number, thousands separator on | `Counts\Status` |
| M3 | `Open Tasks = [Task Count] - [Completed Tasks]` | Whole number, thousands separator on | `Counts\Status` |
| M4 | `Completion % = DIVIDE ( [Completed Tasks], [Task Count] )` | Percentage, 1 decimal place | `Ratios` |
| M5 | `Story Points = SUM ( Task[StoryPoints] )` | **Untouched** | `Counts` |
| M6 | `Estimate Hours = SUM ( Task[EstimateHours] )` | Decimal number, 1 decimal place, thousands separator on | `Hours` |
| M7 | `Actual Hours = SUM ( Task[ActualHours] )` | Decimal number, 1 decimal place, thousands separator on | `Hours` |
| M8 | `Hours Ratio = DIVIDE ( [Actual Hours], [Estimate Hours] )` | **Untouched** | `Ratios` |
| M9 | `Avg Hours per Task = DIVIDE ( [Actual Hours], [Task Count] )` | Decimal number, 2 decimal places, thousands separator off | `Ratios` |
| M10 | `Total Hours = SUM ( 'Time & Expenses'[Hours] )` | Decimal number, 1 decimal place, thousands separator on | `Hours` |
| M11 | `Avg Hours per Person = DIVIDE ( [Total Hours], DISTINCTCOUNT ( 'Time & Expenses'[PersonKey] ) )` | Decimal number, 1 decimal place | `Hours` |
| M12 | `Expense Amount = CALCULATE ( SUM ( 'Time & Expenses'[Amount] ), 'Time & Expenses'[EntryType] = "Expense" )` | Currency, `€ Euro (€ 123)`, 2 decimal places | `Money` |
| M13 | `Budget EUR = SUM ( Project[Budget] )` | Currency, `€ Euro (€ 123)`, 0 decimal places | `Money` |
| M14 | `Portfolio Target Hours = SUM ( 'Portfolio Target'[TargetHours] )` | Whole number, thousands separator on | `Hours` |
| M15 | `Hours (Due Date) = CALCULATE ( [Actual Hours], USERELATIONSHIP ( Task[DueDate], 'Date'[Date] ) )` | Decimal number, 1 decimal place | `Hours` |
| M16 | `Status Color = SWITCH ( SELECTEDVALUE ( Task[Status] ), "Completed", "#20A741", "In progress", "#F2A900", "Blocked", "#D64550", "#A0A0A0" )` | **Untouched** | `Formatting` |
| M17 | `Avg Hourly Rate = AVERAGE ( Person[Hourly Rate] )` | Custom (Model view > Properties > Format: Custom), format string `"€"#,0.00" /h"` (type it with the quotes) | `Money` |

### Home table `Task` (a fact table)

| # | DAX | Format | Display folder |
|---|---|---|---|
| M18 | `Overdue Tasks = CALCULATE ( COUNTROWS ( Task ), Task[Status] <> "Completed", Task[DueDate] < DATE ( 2025, 12, 31 ) )` | Whole number, thousands separator on | (none) |

### Home table `Time & Expenses` (a fact table)

| # | DAX | Format | Display folder |
|---|---|---|---|
| M19 | `Billable Hours = CALCULATE ( SUM ( 'Time & Expenses'[Hours] ), 'Time & Expenses'[IsBillable] = TRUE () )` | Decimal number, 1 decimal place, thousands separator on | (none) |
| M20 | `Entry Count = COUNTROWS ( 'Time & Expenses' )` | Whole number, thousands separator on | (none) |

## 11. Descriptions

Model view > select the object > Properties pane > **Description**. Paste the text exactly.

| Object | Description |
|---|---|
| Table `Task` | `One row per task. Source: Task.csv.` |
| Column `Task[Status]` | `Workflow status: Not started, In progress, Blocked or Completed.` |
| Measure `Task Count` | **Two lines** (see below) |
| Measure `Completed Tasks` | `Tasks with Status = "Completed" & counted once.` |
| Measure `Open Tasks` | `Task Count minus Completed Tasks.` |
| Hierarchy `Date[Calendar]` | `Year > Quarter > Month > Date drill path.` |

`Task Count` two-line description:

```text
Number of tasks in the current filter context.
Counts every Task row, including blocked tasks.
```

Type line 1, press **Shift+Enter** (try **Ctrl+Enter** if Shift+Enter commits the box), then type line 2. If the box won't take a line break, use Desktop's **TMDL view** (left rail) instead: script out `Measures Table`, add the two lines as `///` comments directly above `measure 'Task Count'`, and click **Apply**. Record which way you used in `BUILD-NOTES.md`.

## 12. Theme

1. **View > Themes** (expand the gallery) **> Browse for themes**, pick `Desktop Shapes Theme.json` from the data folder of your clone, open it, dismiss the success message.
2. Save, then look in `04-desktop-shapes.Report\StaticResources\RegisteredResources\` and write the theme file name you see into `BUILD-NOTES.md`.
3. **View > Themes > Customize current theme**. Keep the name `Desktop Shapes Theme`. Go to **Text** and set:

   | Section | Font family | Font size | Font colour |
   |---|---|---|---|
   | General | Segoe UI | 10 | `#3B3A39` |
   | Title | Segoe UI Semibold | 13 | `#1F3A5F` |
   | Cards and KPIs | (leave) | 30 | `#118DFF` |
   | Tab headers | (leave) | (leave) | `#605E5C` |

   Click **Apply**.
4. Save, and record the RegisteredResources file name(s) again in `BUILD-NOTES.md` (Desktop may rename or add a file).

Do this before building visuals, so visuals inherit from the theme and carry no accidental overrides.

## 13. Pages

Rename `Page 1` to `Overview` (double-click the tab), then add pages so the tabs read, in this order:

1. `Overview`
2. `Task Board`
3. `Filter Lab`
4. `Chart Gallery`
5. `Project Detail`
6. `Person Tooltip`
7. `QA Hidden`

Leave the canvas at the default 16:9 size, except `Person Tooltip` (step 13f).

### How to name visuals (read once)

Desktop gives every visual a random 20-character ID, so the fixture identifies visuals by **title text**. For every visual below, the **Title** column is mandatory:

- Select the visual > **Format > General > Title** > **Text** = the title given.
- Where the table says *hidden title*, type the text and then switch the Title toggle **off**. The text is still saved and still identifies the visual.
- Titles must be unique within a page.

Layout isn't under test: place visuals anywhere without overlaps, except where a size and position is given (Format > General > Properties > Size and Position).

### 13a. Page `Overview`

| Title | Visual | Build |
|---|---|---|
| `Overview Header` (hidden title) | Text box | See below. Size and position: X 24, Y 16, Width 640, Height 96. |
| `Overview Link` (hidden title) | Text box | See below. |
| `Team Logo Image` (hidden title) | Image | **Insert > Image**, pick `Team Logo.png` from the data folder. Size and position: X 1160, Y 16, Width 96, Height 32. Format > Image > **Image fit**: Fit (the default in current builds, written as `fit`; older builds call it Scaling). |
| `Delivery KPIs` | Card (the **new** card, `cardVisual`) | See below. |
| `Tasks by Status` | Stacked column chart | X-axis `Project[Portfolio]`, Y-axis `Task Count`, Legend `Task[Status]`. Colours below. |
| `Portfolio Slicer` (hidden title) | Slicer | Field `Project[Portfolio]`. Format > Slicer settings > Options > Style: Vertical list. No selection. Sync in step 13b. |
| `Page Navigator` (hidden title) | Page navigator | **Insert > Buttons > Navigator > Page navigator**. Defaults. |

**Overview Header** text box. Type the text, then select each piece and format it with the text box toolbar (colour: font colour > More colours > hex).

- Paragraph 1, one run: `Delivery Overview`: font **Georgia**, size **24**, **bold**, colour `#1F3A5F`.
- Press **Enter** for a new paragraph.
- Paragraph 2, run A: `Portfolio status for ` (ends with a space): Segoe UI, 12, not bold, colour `#605E5C`.
- Paragraph 2, run B: `2024-2025`: Segoe UI, 12, **bold** and *italic*, colour `#D64550`. Type it straight after run A, **without** pressing Enter: runs A and B must share one paragraph.

**Overview Link** text box: type `Open the project handbook`. Select only `project handbook` and click the link button in the text box toolbar; URL `https://example.com/handbook`. Leave `Open the ` unformatted.

**Delivery KPIs** card. Use the card visual that Desktop currently calls **Card** (in older builds **Card (new)**), not **Card (legacy)**. After step 15 the visual's `visualType` must be `cardVisual`.

1. Data: `Task Count`, `Completion %`, `Total Hours`, `Expense Amount`, in that order.
2. Reference label: add `Open Tasks` as a reference label (Build pane **Reference labels** well, or Format > **Reference labels > Add**, depending on build). If your build can attach it to one series, attach it to `Task Count`.
3. Format > Layout: arrange the 4 tiles in a single row (horizontal), if the option exists.
4. At the top of the Format pane, use **Apply settings to > Series** to format each measure separately:

   | Series | Cards > Accent bar | Callout value font size | Label font colour |
   |---|---|---|---|
   | Task Count | on, `#118DFF` | 28 | `#1F3A5F` |
   | Completion % | on, `#20A741` | 24 | `#20A741` |
   | Total Hours | on, `#F2A900` | 24 | `#605E5C` |
   | Expense Amount | on, `#D64550` | 20 | `#D64550` |

5. Callout area: if your build has a **Callout area** setting (under Callout values or Layout), set series `Task Count` callout area background to `#EAF3FF`. If it doesn't exist, skip it and record that.
6. With **Apply settings to > All**: Cards > Background colour `#F7F9FC`.

**Tasks by Status** colours: Format > Columns > Colors, then per series (use the series dropdown, or the per-series list):

| Series (Task[Status]) | Colour |
|---|---|
| Completed | `#20A741` |
| In progress | `#F2A900` |
| Not started | `#A0A0A0` |
| Blocked | `#D64550` |

Desktop writes no colour entry when the colour picked equals the theme's default for that series or category (for example `Actual Hours` `#1F3A5F` and `Engineering` `#118DFF` in step 13d). That's expected; don't pick a different colour.

### 13b. Page `Task Board`

| Title | Visual | Build |
|---|---|---|
| `Portfolio Slicer` (hidden title) | Slicer | Set the sync group name on the Overview slicer first (step 1 below), then copy it (Ctrl+C), go to Task Board, paste (Ctrl+V). When Desktop asks whether to sync, click **Sync**. |
| `Priority Slicer` (hidden title) | Slicer | Field `Project[Priority]`. Vertical list. Format > Slicer settings > Selection: **Single select** on. Selection is set in step 14. |
| `Status Slicer` (hidden title) | Slicer | Field `Task[Status]`. Vertical list. Selection: Single select off, Multi-select with Ctrl on. Selection is set in step 14. |
| `Team Slicer` (hidden title) | Slicer | Field `Person[Team]`. Vertical list. Selection: Single select off, **Show "Select all" option** on. Selection is set in step 14. |
| `Date Range Slicer` (hidden title) | Slicer | Field `Date[Date]`. Style: **Between**. Range is set in step 14. |
| `Portfolio Matrix` | Matrix | Rows: hierarchy `Project[Portfolio Tree]` (both levels). Columns: `Task[Status]`. Values: `Task Count`, `Completion %`. Click **Expand all down one level** in the visual header once so project rows show. Format > Row subtotals: on, Position **Bottom**, Subtotal label `Portfolio total`. Column subtotals: on. Conditional formatting below. |
| `People Hours` | Table | Columns: `Person[PersonName]`, `Person[Team]`, `Total Hours`, `Task Count`. Click the `Total Hours` header until it sorts **descending**. Conditional formatting: `Total Hours` > **Data bars**, positive bar colour `#118DFF`. |
| `Task Board Views Navigator` (hidden title) | Bookmark navigator | Created in step 13h. |

**Sync group**:

1. Before copying: on `Overview`, select `Portfolio Slicer`, open **View > Sync slicers**, expand **Advanced options**: group name `PortfolioSync`; tick **Sync field changes to other slicers** and **Sync filter changes to other slicers**. Then copy and paste it to Task Board as above.
2. Select the `Portfolio Slicer` on Task Board. In the pane: `Overview` sync ✓ visible ✓, `Task Board` sync ✓ visible ✓, `Chart Gallery` sync ✓ visible **✗** (Desktop adds a hidden synced slicer there). Leave other pages unticked.
3. Don't rename the group once pages are synced: Desktop moves only the selected slicer to the new group and adds new copies to the other pages, leaving the old ones in the old group. If that happens, delete the old copies (the hidden one through **View > Selection**) so each page has one `Portfolio Slicer`.

**Portfolio Matrix** conditional formatting (Values well > field dropdown > **Conditional formatting**):

1. `Task Count` > **Background colour** > Format style **Rules**, based on `Task Count`:
   - If value >= `0` (Number) and < `5` (Number) then `#F3F2F1`
   - If value >= `5` (Number) and < `15` (Number) then `#FFE699`
   - If value >= `15` (Number) and <= highest value then `#A9D18E`
2. `Task Count` > **Font colour** > Format style **Field value**, based on field `Status Color` (Measures Table).
3. `Completion %` > **Font colour** > Format style **Gradient**, based on `Completion %`: Minimum = Lowest value `#D64550`; tick **Add a middle colour**: Center = Number `0.5` `#F2A900`; Maximum = Highest value `#20A741`.

### 13c. Page `Filter Lab`

Build `Filter - Integer Measure` first, then copy-paste it and swap fields for the others. Each visual's filter goes in **Filters pane > Filters on this visual**; on the measure's card, use **Show items when the value**, pick the operator, type the value, click **Apply filter**.

| Title | Visual | Fields | Visual-level filter |
|---|---|---|---|
| `Filter - Integer Measure` | Table | `Project[ProjectName]`, `Task Count` | `Task Count` **is greater than or equal to** `1` |
| `Filter - Decimal Measure` | Table | `Project[ProjectName]`, `Avg Hours per Task` | `Avg Hours per Task` **is greater than** `1.5` |
| `Filter - No Format Integer` | Table | `Project[ProjectName]`, `Story Points` | `Story Points` **is greater than or equal to** `10` |
| `Filter - No Format Decimal` | Table | `Project[ProjectName]`, `Hours Ratio` | `Hours Ratio` **is greater than or equal to** `0.95` |
| `Filter - Currency Measure` | Table | `Project[ProjectName]`, `Expense Amount` | `Expense Amount` **is greater than** `500` |
| `Filter - Percent Measure` | Table | `Project[ProjectName]`, `Completion %` | `Completion %` **is greater than** `0.5` (type `0.5`, not `50%`) |
| `Filter - Numeric Column` | Table | `Task[TaskCode]`, `Task[StoryPoints]` (Values well dropdown > **Don't summarize**) | On the `StoryPoints` card: Filter type **Advanced filtering**, **is greater than or equal to** `3` |
| `Filter - Top N` | Clustered bar chart | Y-axis `Person[PersonName]`, X-axis `Total Hours` | On the `PersonName` card: Filter type **Top N**, Show items **Top** `5`, By value: drag `Total Hours` in. Then sort the chart by `PersonName` **ascending** (visual header > More options > Sort axis). Tooltip page in step 13f. |
| `Filter - Relative Date` | Line chart | X-axis `Date[Date]` (the column, not the `Calendar` hierarchy), Y-axis `Task Count` | Drag `Date[Date]` to this visual's filters if it isn't there. Filter type **Relative date**: **is in the last** `3` **years**, **Include today** ticked. |

Page-level filter: drag `Project[IsActive]` to **Filters on this page**, Basic filtering, tick `True` only.

### 13d. Page `Chart Gallery`

| Title | Visual | Build |
|---|---|---|
| `Hours by Measure Series` | Clustered column chart | X-axis `Project[Portfolio]`, Y-axis `Estimate Hours` then `Actual Hours`. Format > Columns > Colors, per series: `Estimate Hours` `#A0C4FF`, `Actual Hours` `#1F3A5F`. |
| `Hours by Team` | Clustered bar chart | Y-axis `Person[Team]`, X-axis `Total Hours`. No legend. Format > Bars > Colors > **Show all** on, then: Design `#8E6CEF`, Engineering `#118DFF`, QA `#20A741`, Operations `#F2A900`. |
| `Billable Split` | Donut chart | Legend `Time & Expenses[IsBillable]`, Values `Total Hours`. Format > Slices > Colors: `True` `#20A741`, `False` `#A0A0A0`. |
| `Tasks per Story Points` | Clustered column chart | X-axis `Task[StoryPoints]`, Y-axis `Task Count`. Format > X-axis > Type **Categorical**. Format > Columns > Colors > **Show all** on, set only the `13` column to `#D64550`. |
| `Hours Trend` | Line and clustered column chart | X-axis `Date[YearMonth]`, Column y-axis `Total Hours`, Line y-axis `Completion %`. Sort by `YearMonth` ascending. |
| `Hours vs Tasks` **(optional)** | Scatter chart | Values `Project[ProjectName]`, X-axis `Task Count`, Y-axis `Total Hours`, Size `Expense Amount`. |
| `Hours Treemap` **(optional)** | Treemap | Category `Project[Portfolio]`, Details `Project[ProjectName]`, Values `Total Hours`. |

The hidden synced `Portfolio Slicer` from step 13b also lives on this page; leave it alone.

### 13e. Page `Project Detail` (drillthrough)

1. Click an empty part of the canvas. In the **Visualizations > Build** pane, **Drill through** section: drag `Project[ProjectName]` into the drill-through well. **Keep all filters**: on. Cross-report: off.
2. Desktop adds a back button. Give it title text `Back Button` (hidden title).
3. Add:

| Title | Visual | Build |
|---|---|---|
| `Project KPIs` | Card (new, `cardVisual`) | Data: `Task Count`, `Total Hours`, `Budget EUR`. No per-series formatting. |
| `Project Tasks` | Table | `Task[TaskCode]`, `Task[TaskName]`, `Task[Status]`, `Task[Duration Band]`, `Task[DueDate]`, `Task[ActualHours]` (Sum). Sort by `DueDate` ascending. |
| `Tags on Project` | Clustered bar chart | Y-axis `Tag[TagName]`, X-axis `Task Count`. |
| `Q/A Review` | Table | `Q/A Notes[Reviewer]`, `Q/A Notes[ReviewDate]`, `Q/A Notes[QAScore]`, `Q/A Notes[Note]`. |
| `Portfolio Target` | Card (new, `cardVisual`) | Data: `Portfolio Target Hours`. |

### 13f. Page `Person Tooltip` (tooltip page)

1. With nothing selected: Format > **Page information** > **Allow use as tooltip** on. Format > **Canvas settings** > Type **Tooltip**.
2. Build pane > **Tooltip** well (appears once the page allows tooltips): drag `Person[PersonName]` in. Keep all filters: on.
3. Add:

| Title | Visual | Build |
|---|---|---|
| `Tooltip KPIs` | Card (new, `cardVisual`) | Data: `Total Hours`, `Task Count`. |
| `Tooltip Status Mix` | Clustered column chart | X-axis `Task[Status]`, Y-axis `Task Count`. |

4. Right-click the page tab > **Hide page**.
5. Go to `Filter Lab`, select `Filter - Top N` > Format > General > **Tooltips**: Type **Report page**, Page `Person Tooltip`.

### 13g. Page `QA Hidden`

1. Right-click the tab > **Hide page**.
2. With this page open: **Modeling > New parameter > Fields**. Name `Metric Selector`. Add fields in this order: `Total Hours`, `Task Count`, `Expense Amount`. Keep **Add slicer to this page** ticked. Click **Create**.
3. Visuals:

| Title | Visual | Build |
|---|---|---|
| `Metric Selector Slicer` (hidden title) | Slicer | The slicer Desktop just created. Leave it as created. |
| `Metric by Portfolio` | Clustered column chart | X-axis `Project[Portfolio]`, Y-axis `Metric Selector[Metric Selector]` (the field parameter column). |
| `QA Note` (hidden title) | Text box | Type `Hidden page for fixture QA.` No formatting at all (default style, for comparison with the Overview text boxes). |
| `Status Colors Table` | Table | `Status Colors[Status]`, `Status Colors[Hex]`, `Status Colors[Sort]` (Don't summarize). |
| `Owner Info Table` | Table | All five columns of `Owner's Info`. |
| `Rates Table` | Table | `Rates (EUR)[Role]`, `Rates (EUR)[HourlyRate]` (Don't summarize). |
| `QA Frame` **(optional)** (hidden title) | Shape | **Insert > Shapes > Rounded rectangle**. Format > Shape > Fill colour `#F7F9FC`, Border colour `#E0E0E0`. |

### 13h. Bookmarks

Open **View > Bookmarks** and **View > Selection**.

1. Go to `Task Board`. In `Status Slicer`, clear any selection (eraser icon). **Add** a bookmark, rename it (`...` > Rename) to `Task Board - All Statuses`.
2. In `Status Slicer`, select only `Blocked`. Add a bookmark named `Task Board - Blocked Only`.
3. Ctrl-click both bookmarks > `...` > **Group**. Rename the group to `Task Board Views`.
4. On `Task Board`: **Insert > Buttons > Navigator > Bookmark navigator**. Format > Bookmarks > **Bookmark group** `Task Board Views`. Title text `Task Board Views Navigator` (hidden title).
5. Go to `Overview`. In the Selection pane, click the eye icon of `Team Logo Image` to hide it. Add a bookmark named `Overview - Hide Logo`. On that bookmark's `...` menu, untick **Data** (keep Display and Current page ticked). Then show the logo again (eye icon).

## 14. Saved Slicer Selections (Do This Last)

These selections are saved with the report and must be the final state. Bookmarks don't change them.

| Page | Slicer | Final state |
|---|---|---|
| Task Board | `Priority Slicer` | `High` selected (single select) |
| Task Board | `Status Slicer` | `In progress` and `Blocked` selected (Ctrl+click) |
| Task Board | `Team Slicer` | Click **Select all**, then click `Design` to deselect it. Every team except Design is ticked (an inverted "all except" selection). |
| Task Board | `Date Range Slicer` | Start **1 March 2024**, end **30 June 2025**. Use the calendar pickers, or type the dates in your Windows date format (`3/1/2024` and `6/30/2025` on en-US). |
| Overview / Task Board | `Portfolio Slicer` | Nothing selected |

Then click the `Overview` tab so it's the page the report opens on, and save.

## 15. Save, Reopen, Verify Before Committing

1. Save (Ctrl+S), close Desktop, reopen `04-desktop-shapes.pbip`. Check that it opens without errors or repair prompts, and that `Overview` shows data. Close without changing anything (if Desktop asks to save, choose **Don't save**).
2. From a shell in the repo root (WSL or Git Bash), run:

```bash
F=fixtures/real-report-fixtures/report-04-desktop-shapes
# Remove Windows download markers (only present if files were copied via a WSL path)
find "$F" -name '*:Zone.Identifier' -print -delete
# PBIR + TMDL, not legacy formats
test -d "$F/04-desktop-shapes.Report/definition/pages" && echo "PBIR ok"
test -d "$F/04-desktop-shapes.SemanticModel/definition/tables" && echo "TMDL ok"
test ! -e "$F/04-desktop-shapes.SemanticModel/model.bim" && echo "no model.bim ok"
# 7 page folders
find "$F/04-desktop-shapes.Report/definition/pages" -name page.json | wc -l
# Table files: expect 21 (10 CSV + Measures Table + 9 calculated + Metric Selector)
ls "$F/04-desktop-shapes.SemanticModel/definition/tables" | wc -l
ls "$F/04-desktop-shapes.SemanticModel/definition/tables"
# 12 relationships
grep -c '^relationship ' "$F/04-desktop-shapes.SemanticModel/definition/relationships.tmdl"
# Descriptions (/// lines): expect at least 7
grep -rn '^\s*///' "$F/04-desktop-shapes.SemanticModel/definition" | wc -l
# Sync group on 3 slicers
grep -rl '"syncGroup"' "$F/04-desktop-shapes.Report/definition/pages" | wc -l
# New card visuals: expect 4
grep -rl '"visualType": "cardVisual"' "$F/04-desktop-shapes.Report/definition/pages" | wc -l
# Theme and image resources
ls "$F/04-desktop-shapes.Report/StaticResources/RegisteredResources"
# Bookmarks: 3 bookmark files
ls "$F/04-desktop-shapes.Report/definition/bookmarks"
```

3. Check by eye:
   - `relationships.tmdl` has one relationship with a `toCardinality: many` line (R12) and one with `fromCardinality: one` (R11), one with `crossFilteringBehavior: bothDirections` (R9; R11 may have it too) and one with `isActive: false` (R2).
   - `Measures Table.tmdl` (or however Desktop names it) contains the `///` two-line description above `measure 'Task Count'`.
   - The `Overview Header` text box JSON contains two paragraphs, three text runs, and the colours `#1F3A5F` and `#D64550`.
4. **Don't commit** `*/.pbi/cache.abf` or `*/.pbi/localSettings.json`. Desktop's own `.gitignore` (written next to the `.pbip`) excludes them; keep that `.gitignore` and commit it. Commit everything else exactly as Desktop wrote it, including `.platform`, `definition.pbism`, `diagramLayout.json` and `.pbi/editorSettings.json`.
5. Optional, for `BUILD-NOTES.md` only (don't fix anything it reports; several findings are the open issues this fixture exists for):

```bash
uv run pbi validate -p "$F/04-desktop-shapes.pbip"
uv run pbi map -p "$F/04-desktop-shapes.pbip"
```

## 16. Rename Snapshot (issue #55)

Do this after step 15, from the saved state. If the original changes later, delete this folder and make the snapshot again from the new state, so the two folders differ only by the renames.

1. Create `fixtures\real-report-fixtures\report-04-desktop-shapes-renamed\`.
2. Copy into it: `04-desktop-shapes.pbip`, the `04-desktop-shapes.Report` folder, the `04-desktop-shapes.SemanticModel` folder and `.gitignore`. Don't copy `data`, `SPEC.md`, `BUILD-CHECKLIST.md` or `BUILD-NOTES.md`.
3. Open the **copy's** `04-desktop-shapes.pbip`.
4. In the Data pane, right-click measure `Total Hours` (Measures Table) > **Rename** > `Hours Logged`.
5. Right-click column `Person[PersonName]` > **Rename** > `Person Name`.
6. Change nothing else. Save, close.
7. Run the Zone.Identifier `find` from step 15 on the new folder too.
8. Check the renames were saved: `grep -rl "Hours Logged" fixtures/real-report-fixtures/report-04-desktop-shapes-renamed` must list files, and `diff -rq` against the original must show differences.

Where the renamed objects are used (no action needed; this is what the snapshot captures):

- `Total Hours`: `Delivery KPIs` (card tile), `People Hours` (column, sort, data bars), `Filter - Top N` (value and the top-N "By value"), `Hours by Team`, `Billable Split`, `Hours Trend`, `Tooltip KPIs`, `Project KPIs`, the `Avg Hours per Person` measure DAX, and the `Metric Selector` field parameter DAX.
- `Person[PersonName]`: `People Hours` (column), `Filter - Top N` (axis, axis sort and the top-N filter field), and the `Person Tooltip` page's tooltip field.

## 17. Build Notes

Create `fixtures/real-report-fixtures/report-04-desktop-shapes/BUILD-NOTES.md` and commit it with the fixture:

```markdown
# Build Notes: Report 04 Desktop Shapes

- Power BI Desktop version: <Help > About, full version and month>
- Built on: <date>, Windows path <C:\...>
- Preview features ticked in step 1.4: <list, or "not listed">
- Theme file in RegisteredResources after import (step 12.2): <file name>
- Theme file(s) after customize (step 12.4): <file name(s)>
- Image file in RegisteredResources: <file name>
- Multi-line description entered via: <Properties pane with Shift+Enter | Ctrl+Enter | TMDL view>
- Table names Desktop refused, and what was used instead: <none | ...>
- Steps skipped or impossible (step number and reason): <none | ...>
- Optional steps done: <list>
- Rename snapshot (step 16) done: <yes/no>
- `pbi validate` summary (optional): <paste the summary line(s)>
- Anything else that looked different from this checklist: <...>
```

## 18. Commit

On a branch, not `master`: `git add` the fixture folder(s) and `BUILD-NOTES.md`, check `git status` shows no `cache.abf`, `localSettings.json` or `Zone.Identifier` files, and commit (for example `test(fixtures): add desktop-built report-04 fixture`).
