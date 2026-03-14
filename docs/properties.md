# Properties Reference

All properties usable with `pbi visual set` and `pbi visual get`. Use `pbi visual properties` for a quick listing.

## Position Properties

Direct values (not PBI-encoded):

| Property | Type | Description |
|----------|------|-------------|
| `position.x` | number | X coordinate |
| `position.y` | number | Y coordinate |
| `position.width` | number | Width |
| `position.height` | number | Height |
| `position.z` | number | Z-order (stacking) |
| `position.tabOrder` | number | Keyboard tab sequence |
| `position.angle` | number | Rotation angle |

## Core Properties

| Property | Type | Description |
|----------|------|-------------|
| `visualType` | string | Chart type identifier |
| `isHidden` | boolean | Hidden in view mode |

## Container Formatting

Encoded as PBI visual container objects (`visualContainerObjects`):

| Property | Type | Description |
|----------|------|-------------|
| **Background** | | |
| `background.show` | boolean | Show background |
| `background.color` | color | Background color (`#hex`) |
| `background.transparency` | number | 0-100 |
| **Border** | | |
| `border.show` | boolean | Show border |
| `border.color` | color | Border color |
| `border.width` | number | Border width |
| `border.radius` | number | Corner radius |
| **Title** | | |
| `title.show` | boolean | Show title |
| `title.text` | string | Title text |
| `title.heading` | string | Title heading level |
| `title.wrap` | boolean | Wrap title text |
| `title.color` | color | Title font color |
| `title.background` | color | Title background color |
| `title.alignment` | enum | `left`, `center`, `right` |
| `title.fontSize` | number | Title font size |
| `title.fontFamily` | string | Title font family |
| `title.bold` | boolean | Bold title |
| `title.italic` | boolean | Italic title |
| `title.underline` | boolean | Underline title |
| **Subtitle** | | |
| `subtitle.show` | boolean | Show subtitle |
| `subtitle.text` | string | Subtitle text |
| `subtitle.heading` | string | Subtitle heading level |
| `subtitle.wrap` | boolean | Wrap subtitle text |
| `subtitle.color` | color | Subtitle font color |
| `subtitle.alignment` | enum | `left`, `center`, `right` |
| `subtitle.fontSize` | number | Subtitle font size |
| `subtitle.fontFamily` | string | Subtitle font family |
| `subtitle.bold` | boolean | Bold subtitle |
| `subtitle.italic` | boolean | Italic subtitle |
| `subtitle.underline` | boolean | Underline subtitle |
| **Divider** | | |
| `divider.show` | boolean | Show divider between title and visual |
| `divider.color` | color | Divider color |
| `divider.width` | number | Divider width |
| `divider.style` | string | Divider line style |
| `divider.ignorePadding` | boolean | Divider ignores padding |
| **Spacing** | | |
| `spacing.customize` | boolean | Enable custom spacing |
| `spacing.vertical` | number | Vertical spacing |
| `spacing.belowTitle` | number | Space below title |
| `spacing.belowSubtitle` | number | Space below subtitle |
| `spacing.belowTitleArea` | number | Space below title area |
| **Padding** | | |
| `padding.top` | number | Top padding |
| `padding.bottom` | number | Bottom padding |
| `padding.left` | number | Left padding |
| `padding.right` | number | Right padding |
| **Drop Shadow** | | |
| `shadow.show` | boolean | Show drop shadow |
| `shadow.preset` | string | Shadow preset |
| `shadow.position` | string | Shadow position |
| `shadow.color` | color | Shadow color |
| `shadow.transparency` | number | Shadow transparency |
| `shadow.spread` | number | Shadow spread |
| `shadow.blur` | number | Shadow blur |
| `shadow.angle` | number | Shadow angle |
| `shadow.distance` | number | Shadow distance |
| **Visual Header** | | |
| `header.show` | boolean | Show visual header |
| `header.background` | color | Header background color |
| `header.border` | color | Header border color |
| `header.transparency` | number | Header transparency |
| `header.foreground` | color | Header icon color |
| **Tooltip** | | |
| `tooltip.show` | boolean | Show tooltip |
| `tooltip.type` | string | Tooltip type (`Default` or `ReportPage`) |
| `tooltip.section` | string | Tooltip report page name |
| `tooltip.titleColor` | color | Tooltip title font color |
| `tooltip.valueColor` | color | Tooltip value font color |
| `tooltip.fontSize` | number | Tooltip font size |
| `tooltip.fontFamily` | string | Tooltip font family |
| `tooltip.background` | color | Tooltip background color |
| `tooltip.transparency` | number | Tooltip transparency |
| **Button Actions** (actionButton, shape, image) | | |
| `action.show` | boolean | Enable button action |
| `action.type` | string | `Back`, `Bookmark`, `Drillthrough`, `PageNavigation`, `QnA`, `WebUrl` |
| `action.bookmark` | string | Target bookmark name |
| `action.page` | string | Target page name (folder name) |
| `action.drillthrough` | string | Target drillthrough page |
| `action.url` | string | Target URL |
| `action.tooltip` | string | Button tooltip text |
| **Other** | | |
| `lockAspect` | boolean | Lock aspect ratio |
| `altText` | string | Accessibility alt text |
| `stylePreset` | string | Style preset name |

## Chart Formatting

Encoded as PBI visual objects (`visual.objects`). Applies to charts, tables, slicers, KPIs, gauges.

### Legend

Bar, column, line, area, combo, pie, donut, scatter, waterfall, ribbon, funnel, treemap:

| Property | Type | Description |
|----------|------|-------------|
| `legend.show` | boolean | Show legend |
| `legend.position` | enum | `Top`, `Bottom`, `Left`, `Right`, `TopCenter`, `BottomCenter` |
| `legend.color` | color | Legend text color |
| `legend.fontSize` | number | Legend font size |
| `legend.fontFamily` | string | Legend font family |
| `legend.bold` | boolean | Legend bold |
| `legend.italic` | boolean | Legend italic |
| `legend.showTitle` | boolean | Show legend title |
| `legend.titleText` | string | Legend title text |

### Category Axis / X-Axis

Bar, column, line, area, combo, waterfall, ribbon:

| Property | Type | Description |
|----------|------|-------------|
| `xAxis.show` | boolean | Show category axis |
| `xAxis.position` | enum | `Left`, `Right` |
| `xAxis.title` | boolean | Show axis title |
| `xAxis.titleText` | string | Axis title text |
| `xAxis.titleColor` | color | Axis title color |
| `xAxis.titleFontSize` | number | Axis title font size |
| `xAxis.titleFontFamily` | string | Axis title font family |
| `xAxis.color` | color | Axis label color |
| `xAxis.fontSize` | number | Axis label font size |
| `xAxis.fontFamily` | string | Axis label font family |
| `xAxis.bold` | boolean | Axis labels bold |
| `xAxis.italic` | boolean | Axis labels italic |
| `xAxis.axisScale` | enum | `linear`, `log` |
| `xAxis.axisType` | enum | `Scalar`, `Categorical` |
| `xAxis.axisStyle` | enum | `showTitleOnly`, `showUnitOnly`, `showBoth` |
| `xAxis.start` | number | Axis range start |
| `xAxis.end` | number | Axis range end |
| `xAxis.displayUnits` | string | Display units (`0`=Auto, `1`=None, `1000`=K, `1000000`=M) |
| `xAxis.precision` | number | Decimal places |
| `xAxis.gridlines` | boolean | Show gridlines |
| `xAxis.gridlineColor` | color | Gridline color |
| `xAxis.gridlineStyle` | enum | `dashed`, `solid`, `dotted` |
| `xAxis.gridlineThickness` | number | Gridline thickness |
| `xAxis.innerPadding` | number | Inner padding between columns/bars |
| `xAxis.concatenateLabels` | boolean | Concatenate category labels |
| `xAxis.invertAxis` | boolean | Invert axis order |

### Value Axis / Y-Axis

Bar, column, line, area, combo, scatter, waterfall, ribbon:

| Property | Type | Description |
|----------|------|-------------|
| `yAxis.show` | boolean | Show value axis |
| `yAxis.position` | enum | `Left`, `Right` |
| `yAxis.title` | boolean | Show axis title |
| `yAxis.titleText` | string | Axis title text |
| `yAxis.titleColor` | color | Axis title color |
| `yAxis.titleFontSize` | number | Axis title font size |
| `yAxis.titleFontFamily` | string | Axis title font family |
| `yAxis.color` | color | Axis label color |
| `yAxis.fontSize` | number | Axis label font size |
| `yAxis.fontFamily` | string | Axis label font family |
| `yAxis.bold` | boolean | Axis labels bold |
| `yAxis.italic` | boolean | Axis labels italic |
| `yAxis.axisScale` | enum | `linear`, `log` |
| `yAxis.axisStyle` | enum | `showTitleOnly`, `showUnitOnly`, `showBoth` |
| `yAxis.start` | number | Axis range start |
| `yAxis.end` | number | Axis range end |
| `yAxis.displayUnits` | string | Display units (`0`=Auto, `1`=None, `1000`=K, `1000000`=M) |
| `yAxis.precision` | number | Decimal places |
| `yAxis.gridlines` | boolean | Show gridlines |
| `yAxis.gridlineColor` | color | Gridline color |
| `yAxis.gridlineStyle` | enum | `dashed`, `solid`, `dotted` |
| `yAxis.gridlineThickness` | number | Gridline thickness |
| `yAxis.invertAxis` | boolean | Invert value axis |

### Secondary Y-Axis

Combo charts:

| Property | Type | Description |
|----------|------|-------------|
| `y2Axis.show` | boolean | Show secondary axis |
| `y2Axis.position` | enum | `Left`, `Right` |
| `y2Axis.title` | boolean | Show axis title |
| `y2Axis.titleText` | string | Axis title text |
| `y2Axis.titleColor` | color | Axis title color |
| `y2Axis.titleFontSize` | number | Axis title font size |
| `y2Axis.color` | color | Axis label color |
| `y2Axis.fontSize` | number | Axis label font size |
| `y2Axis.fontFamily` | string | Axis label font family |
| `y2Axis.axisScale` | enum | `linear`, `log` |
| `y2Axis.start` | number | Axis range start |
| `y2Axis.end` | number | Axis range end |
| `y2Axis.displayUnits` | string | Display units |
| `y2Axis.precision` | number | Decimal places |
| `y2Axis.gridlines` | boolean | Show gridlines |
| `y2Axis.gridlineColor` | color | Gridline color |

### Data Labels

Most chart types:

| Property | Type | Description |
|----------|------|-------------|
| `labels.show` | boolean | Show data labels |
| `labels.color` | color | Label color |
| `labels.fontSize` | number | Label font size |
| `labels.fontFamily` | string | Label font family |
| `labels.bold` | boolean | Label bold |
| `labels.italic` | boolean | Label italic |
| `labels.position` | enum | `Auto`, `InsideEnd`, `OutsideEnd`, `InsideCenter`, `InsideBase` |
| `labels.format` | string | Display units (`0`=Auto, `1000`=K, `1000000`=M) |
| `labels.precision` | number | Decimal places |
| `labels.labelStyle` | enum | `Data`, `Category`, `Percent of total`, `All detail labels` (pie/donut) |
| `labels.enableBackground` | boolean | Enable label background |
| `labels.backgroundColor` | color | Label background color |
| `labels.backgroundTransparency` | number | Label background transparency |
| `labels.labelDensity` | number | Label density (how many labels to show) |

### Plot Area & Data Colors

| Property | Type | Description |
|----------|------|-------------|
| `plotArea.transparency` | number | Plot area transparency |
| `plotArea.color` | color | Plot area background |
| `dataColors.default` | color | Default data color |
| `dataColors.showAll` | boolean | Show all data colors |

### Line & Area Charts

| Property | Type | Description |
|----------|------|-------------|
| `line.show` | boolean | Show line markers |
| `line.style` | enum | `solid`, `dashed`, `dotted` |
| `line.width` | number | Line stroke width |
| `line.stepped` | boolean | Stepped line (step chart) |
| `line.shadeArea` | boolean | Shade area under line |
| `shapes.showMarkers` | boolean | Show data point markers |
| `shapes.markerShape` | string | Marker shape |
| `shapes.markerSize` | number | Marker size |

### Pie & Donut

| Property | Type | Description |
|----------|------|-------------|
| `slices.innerRadius` | number | Donut inner radius (0 = pie, higher = larger hole) |

### Shape Visual

| Property | Type | Description |
|----------|------|-------------|
| `shape.type` | enum | `rectangle`, `roundedRectangle`, `oval`, `triangle`, `pentagon`, `hexagon`, `octagon`, `arrow`, `star5`, `heart`, `diamond`, etc. |
| `shape.fill` | color | Fill color |
| `shape.fillShow` | boolean | Show fill |
| `shape.fillTransparency` | number | Fill transparency (0-100) |
| `shape.lineColor` | color | Line/border color |
| `shape.lineShow` | boolean | Show line/border |
| `shape.lineWeight` | number | Line weight |
| `shape.lineTransparency` | number | Line transparency (0-100) |
| `shape.roundEdge` | number | Corner rounding |
| `shape.rotation` | number | Rotation angle |

### Image Visual

| Property | Type | Description |
|----------|------|-------------|
| `image.url` | string | Image URL |
| `image.scaling` | enum | `Fit`, `Fill`, `Normal` |

### Card Visual (legacy `card`)

| Property | Type | Description |
|----------|------|-------------|
| `categoryLabels.show` | boolean | Show category label |
| `categoryLabels.color` | color | Category label color |
| `categoryLabels.fontSize` | number | Category label font size |
| `categoryLabels.fontFamily` | string | Category label font family |
| `wordWrap.show` | boolean | Enable word wrap |

### Slicer Visual

| Property | Type | Description |
|----------|------|-------------|
| `slicerHeader.show` | boolean | Show slicer header |
| `slicerHeader.fontColor` | color | Header font color |
| `slicerHeader.background` | color | Header background |
| `slicerHeader.fontSize` | number | Header font size |
| `slicerHeader.fontFamily` | string | Header font family |
| `slicerHeader.bold` | boolean | Header bold |
| `slicerItems.fontColor` | color | Items font color |
| `slicerItems.background` | color | Items background |
| `slicerItems.fontSize` | number | Items font size |
| `slicerItems.fontFamily` | string | Items font family |
| `slicer.selectAll` | boolean | Enable select all checkbox |
| `slicer.singleSelect` | boolean | Single selection mode |

### KPI Visual

| Property | Type | Description |
|----------|------|-------------|
| `kpi.showIcon` | boolean | Show KPI status icon |
| `kpi.displayUnits` | string | KPI display units |
| `kpi.precision` | number | KPI decimal places |
| `kpi.direction` | enum | `Positive` (high is good), `Negative` (high is bad) |
| `kpi.goodColor` | color | Good status color |
| `kpi.neutralColor` | color | Neutral status color |
| `kpi.badColor` | color | Bad status color |
| `kpi.showTrendline` | boolean | Show trendline |
| `kpi.showGoal` | boolean | Show goal |
| `kpi.showDistance` | boolean | Show distance to goal |

### Gauge Visual

| Property | Type | Description |
|----------|------|-------------|
| `gauge.max` | number | Gauge maximum value |
| `gauge.target` | number | Gauge target value |
| `gauge.targetColor` | color | Target line color |
| `gauge.targetShow` | boolean | Show target label |
| `gauge.calloutShow` | boolean | Show callout value |
| `gauge.calloutColor` | color | Callout value color |
| `gauge.calloutDisplayUnits` | string | Callout display units |
| `gauge.calloutPrecision` | number | Callout decimal places |

### Waterfall Chart

| Property | Type | Description |
|----------|------|-------------|
| `waterfall.increaseColor` | color | Increase color |
| `waterfall.decreaseColor` | color | Decrease color |
| `waterfall.totalColor` | color | Total color |

### New Card Visual (`cardVisual`)

| Property | Type | Description |
|----------|------|-------------|
| **Layout** | | |
| `layout.style` | string | Card layout (`Cards` or `Callout`) |
| `layout.columnCount` | long | Number of columns |
| `layout.calloutSize` | number | Callout font size |
| **Accent Bar** | | |
| `accentBar.show` | boolean | Show accent bar |
| `accentBar.color` | color | Accent bar color |
| **Card Value** | | |
| `cardValue.fontSize` | number | Value font size |
| `cardValue.fontFamily` | string | Value font family |
| `cardValue.bold` | boolean | Value bold |
| `cardValue.italic` | boolean | Value italic |
| `cardValue.color` | color | Value font color |
| `cardValue.displayUnits` | string | Display units (`0`=Auto, `1000`=K, `1000000`=M) |
| `cardValue.precision` | number | Decimal places |
| **Card Label** | | |
| `cardLabel.show` | boolean | Show label |
| `cardLabel.color` | color | Label font color |
| `cardLabel.fontSize` | number | Label font size |
| `cardLabel.fontFamily` | string | Label font family |
| `cardLabel.bold` | boolean | Label bold |
| `cardLabel.italic` | boolean | Label italic |
| **Card Shape** | | |
| `cardShape.color` | color | Card background color |
| `cardShape.radius` | number | Corner radius |
| `cardShape.transparency` | number | Background transparency |
| **Card Divider** | | |
| `cardDivider.show` | boolean | Show divider between cards |
| `cardDivider.color` | color | Divider color |
| `cardDivider.width` | number | Divider width |
| **Other** | | |
| `cardOverflow.show` | boolean | Enable text overflow |
| `cardPadding.top` | number | Internal top padding |
| `cardPadding.bottom` | number | Internal bottom padding |
| `cardPadding.left` | number | Internal left padding |
| `cardPadding.right` | number | Internal right padding |

### Table & Matrix

**Table/matrix global formatting** (via `pbi visual set`):

| Property | Type | Description |
|----------|------|-------------|
| **Column Headers** | | |
| `columnHeaders.fontColor` | color | Header font color |
| `columnHeaders.backColor` | color | Header background |
| `columnHeaders.fontSize` | number | Header font size |
| `columnHeaders.fontFamily` | string | Header font family |
| `columnHeaders.bold` | boolean | Bold headers |
| `columnHeaders.italic` | boolean | Italic headers |
| `columnHeaders.alignment` | enum | `Left`, `Center`, `Right` |
| `columnHeaders.wordWrap` | boolean | Wrap header text |
| `columnHeaders.autoSize` | boolean | Auto-size column widths |
| **Data Cells** | | |
| `values.fontColor` | color | Cell font color |
| `values.backColor` | color | Primary row background |
| `values.altBackColor` | color | Alternate row background |
| `values.fontSize` | number | Cell font size |
| `values.fontFamily` | string | Cell font family |
| `values.wordWrap` | boolean | Wrap cell text |
| `values.urlIcon` | boolean | Show URL icon |
| **Grid** | | |
| `grid.vertical` | boolean | Show vertical gridlines |
| `grid.verticalColor` | color | Vertical gridline color |
| `grid.verticalWeight` | number | Vertical gridline weight |
| `grid.horizontal` | boolean | Show horizontal gridlines |
| `grid.horizontalColor` | color | Horizontal gridline color |
| `grid.horizontalWeight` | number | Horizontal gridline weight |
| `grid.rowPadding` | number | Row padding |
| `grid.textSize` | number | Grid text size |
| **Totals Row** | | |
| `total.show` | boolean | Show totals row |
| `total.label` | string | Totals row label |
| `total.fontColor` | color | Totals font color |
| `total.backColor` | color | Totals background |
| `total.fontSize` | number | Totals font size |
| `total.fontFamily` | string | Totals font family |
| `total.bold` | boolean | Bold totals |
| **Row Headers (matrix)** | | |
| `rowHeaders.fontColor` | color | Row header font color |
| `rowHeaders.backColor` | color | Row header background |
| `rowHeaders.fontSize` | number | Row header font size |
| `rowHeaders.fontFamily` | string | Row header font family |
| `rowHeaders.bold` | boolean | Bold row headers |
| `rowHeaders.italic` | boolean | Italic row headers |
| `rowHeaders.alignment` | enum | `Left`, `Center`, `Right` |
| `rowHeaders.wordWrap` | boolean | Wrap row header text |
| `rowHeaders.steppedLayout` | boolean | Enable stepped layout |
| `rowHeaders.steppedIndent` | number | Stepped layout indent (px) |
| `rowHeaders.showExpandCollapse` | boolean | Show expand/collapse buttons |
| **Subtotals (matrix)** | | |
| `subTotals.rowSubtotals` | boolean | Show row subtotals |
| `subTotals.columnSubtotals` | boolean | Show column subtotals |
| `subTotals.rowSubtotalsPosition` | enum | `Top`, `Bottom` |
| `subTotals.perRowLevel` | boolean | Per row-level subtotals |
| `subTotals.perColumnLevel` | boolean | Per column-level subtotals |

Any property not listed above can be accessed via raw JSON dot-path (e.g. `visual.objects.legend`).
