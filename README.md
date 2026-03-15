# PBI Report Builder

CLI tool for reading, editing, and managing Power BI PBIP project files (PBIR format). Designed for AI agent automation — hand a report directory to an agent and let it style, bind, and lay out every page programmatically.

## Quick Start

```bash
pbi info                                          # Project overview
pbi page list                                     # List pages
pbi visual list "Sales Overview"                  # List visuals on a page
pbi visual set "Sales" chart1 title.text="Revenue" border.show=true
pbi page export "Sales Overview" -o sales.yaml    # Export page as YAML
pbi apply sales.yaml --dry-run                    # Preview declarative changes
pbi apply sales.yaml                              # Apply changes
cat sales.yaml | pbi apply --dry-run              # Or pipe YAML through stdin
pbi validate                                      # Check structural integrity
```

## Command Groups

| Group | Purpose |
|-------|---------|
| `pbi report` | Report metadata and settings |
| `pbi page` | Page CRUD, reorder, templates, drillthrough, tooltip |
| `pbi visual` | Visual CRUD, styling, grouping, sorting, conditional formatting |
| `pbi nav` | First-class page, bookmark, back, and URL actions |
| `pbi model` | Semantic model tables, columns, measures, DAX |
| `pbi filter` | Report/page/visual filters (categorical, range, Top N, relative date) |
| `pbi theme` | Theme apply/export/delete |
| `pbi bookmark` | Bookmark CRUD |
| `pbi interaction` | Visual cross-filter/highlight interactions |
| `pbi style` | Reusable visual style presets (+ bundled shape presets) |
| `pbi component` | Reusable visual components (grouped widgets with parameters) |
| `pbi image` | Image resource management (add, list, prune) |
| `pbi apply` | Declarative YAML page authoring |
| `pbi map` | Generate full project index as YAML |
| `pbi validate` | Structural validation |
| `pbi capabilities` | Feature support matrix |

## Installation

Requires Python 3.11+.

```bash
# As a global tool
uv tool install -e /path/to/pbi-report-builder

# Or in a virtual environment
cd pbi-report-builder
uv venv && uv pip install -e .
source .venv/bin/activate
```

## Agent Workflow

The recommended workflow for AI agents is export-edit-apply:

```bash
pbi page export "Sales Overview" -o sales.yaml   # Get current state
# Edit the YAML (positions, styles, bindings)
pbi apply sales.yaml --overwrite                  # Apply with full reconciliation
```

YAML-driven commands also accept stdin. Use `-` or pipe content directly into `pbi apply`, `pbi diff`, or `pbi model apply`.

Reusable page templates now support full-page YAML capture plus project/global storage, and button actions have first-class `pbi nav` commands.

See [docs/agent-workflows.md](docs/agent-workflows.md) for detailed patterns.

## Documentation

Detailed guides are in the [docs/](docs/) folder:

- [CLI Reference](docs/pbi-cli-reference.md) — command grammar and common patterns
- [Agent Workflows](docs/agent-workflows.md) — recommended automation patterns
- [Visual Commands](docs/visuals.md) — styling, layout, grouping, formatting
- [Properties Reference](docs/properties.md) — full visual property catalog
- [Capabilities](docs/capabilities.md) — feature support matrix and roadmap
