# Render

Generate HTML layout mockups of report pages with optional PNG screenshots.

## Usage

```bash
pbi render <page> [-p project] [-o output.html] [--screenshot]
```

| Option | Description |
|--------|-------------|
| `<page>` | Page name, display name, or index |
| `-o, --output` | Output HTML path (default: `<PageName>.html` in project root) |
| `-s, --screenshot` | Also generate a PNG via Puppeteer |
| `-p, --project` | Path to PBIP project |

## Examples

```bash
# Render a page as HTML
pbi render "Dashboard" -o dashboard.html

# Render with a PNG screenshot
pbi render "Introduction" -o intro.html --screenshot

# Render by page index
pbi render 3 -o page3.html --screenshot
```

## What Gets Rendered

The mockup accurately captures layout and formatting from the PBIR definition:

- **Position & size** — pixel-accurate absolute coordinates
- **Backgrounds** — solid colors, theme colors, transparency (rgba)
- **Borders** — color, width, radius
- **Drop shadows** — blur, spread, distance
- **Padding** — per-visual
- **Textbox rich text** — font family, size, weight, style, color, alignment per text run
- **Titles** — text, font size, color, alignment (when explicitly shown)
- **Visual groups** — nested groups resolved to absolute page coordinates with correct z-ordering
- **Theme colors** — ThemeDataColor references resolved with lighten/darken percent

Data visuals render as labeled placeholders showing their type and bound field names:

| Visual type | Placeholder content |
|-------------|-------------------|
| Card / KPI | Bound measure name + dash value |
| Table / Matrix | Column headers from bindings |
| Slicer | Field name + dropdown/list icon |
| Button | Text label |
| Shape | Background rectangle |
| Image | Gray placeholder |
| Charts | Type icon + label (e.g. "Bar Chart") |

## Screenshots

The `--screenshot` flag requires Node.js and the `puppeteer` npm package:

```bash
npm install puppeteer
pbi render "Dashboard" --screenshot
```

Screenshots are captured at 2x device pixel ratio using the exact page dimensions from the PBIR definition. The output PNG is saved next to the HTML file with the same name.

## Limitations

- No live data — data visuals show field names, not actual values
- Theme colors use a built-in fallback palette; custom report themes are not loaded
- Images show a gray placeholder (image content is not embedded in PBIR)
- Conditional formatting expressions are not evaluated
