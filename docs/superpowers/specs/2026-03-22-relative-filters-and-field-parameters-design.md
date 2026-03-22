# Design: Relative Date Filters in YAML Apply + Field Parameters

**Date:** 2026-03-22
**Scope:** Two features that close gaps in the core report-building workflow.

---

## Feature 1: Relative Date Filters in YAML Apply

### Problem

The CLI supports relative date/time filters imperatively (`pbi filter create --mode relative`), and the builders (`add_relative_date_filter`, `add_relative_time_filter`) are fully implemented. However, the YAML apply engine (`apply/ops.py:apply_filters_spec`) has no handler for `type: relative`. Agents writing declarative YAML hit a "not yet supported" warning and must fall back to imperative commands or raw filter payloads.

The export side emits `type: RelativeDate` or `type: RelativeTime` with a `raw:` payload, but no structured fields — so even exported filters can't round-trip cleanly through apply without the raw block.

### YAML Syntax

```yaml
filters:
- field: Date.OrderDate
  type: relative
  operator: InLast        # InLast | InThis | InNext
  count: 30
  unit: Days              # Days | Weeks | CalendarWeeks | Months | CalendarMonths | Years | CalendarYears | Minutes | Hours
  includeToday: true      # optional, default true (ignored for time units)
```

### Changes

#### 1. `src/pbi/apply/ops.py` — `apply_filters_spec()`

Add a new branch after the existing `elif filter_type.lower() == "advanced"` block:

```python
elif filter_type.lower() == "relative":
    from pbi.filters import add_relative_date_filter, add_relative_time_filter

    operator = filter_spec.get("operator", "")
    count = filter_spec.get("count")
    unit = filter_spec.get("unit", "")
    include_today = filter_spec.get("includeToday", True)

    time_units = {"Minutes", "Hours"}
    date_units = {"Days", "Weeks", "CalendarWeeks", "Months", "CalendarMonths", "Years", "CalendarYears"}
    all_units = time_units | date_units
    is_time = unit in time_units

    # InThis is only valid for date units, not time units
    valid_ops = {"InLast", "InNext"} if is_time else {"InLast", "InThis", "InNext"}
    if operator not in valid_ops:
        result.errors.append(
            f"{context}: relative filter operator must be one of: {', '.join(sorted(valid_ops))}."
        )
        continue

    if not count or int(count) <= 0:
        result.errors.append(f"{context}: relative filter requires a positive 'count'.")
        continue

    # InThis always uses count=1 — auto-correct if different
    if operator == "InThis":
        count = 1

    if unit not in all_units:
        result.errors.append(
            f"{context}: relative filter unit '{unit}' not recognized. "
            f"Use one of: {', '.join(sorted(all_units))}."
        )
        continue

    field_type_name = "column"
    if project is not None:
        entity, prop, field_type_name, _ = resolve_apply_field(field_ref, project, session=session)

    if field_type_name != "column":
        result.errors.append(f"{context}: relative filters only support column fields, not {field_type_name}.")
        continue

    try:
        if is_time:
            add_relative_time_filter(
                data, entity, prop,
                operator=operator,
                time_units_count=int(count),
                time_unit_type=unit,
                field_type=field_type_name,
                is_hidden=is_hidden,
                is_locked=is_locked,
            )
        else:
            add_relative_date_filter(
                data, entity, prop,
                operator=operator,
                time_units_count=int(count),
                time_unit_type=unit,
                include_today=bool(include_today),
                field_type=field_type_name,
                is_hidden=is_hidden,
                is_locked=is_locked,
            )
        result.filters_added += 1
    except (ValueError, NotImplementedError) as e:
        result.errors.append(f"{context}: {e}")
```

#### 2. `src/pbi/export.py` — `_export_filters()`

Enrich the export for RelativeDate/RelativeTime filters. After building the base `entry` dict, detect relative filters and add structured fields so they round-trip without needing the `raw:` block:

```python
if info.filter_type in ("RelativeDate", "RelativeTime"):
    entry["type"] = "relative"  # normalize to the apply-compatible name
    # Extract operator, count, unit from the parsed condition
    summary = _extract_relative_structured(f)
    if summary:
        entry.update(summary)  # adds operator, count, unit, includeToday
        del entry["raw"]       # structured fields are sufficient
```

Add a helper `_extract_relative_structured()` that reverses the condition structure back to `{operator, count, unit, includeToday}`. This mirrors the logic already in `_extract_relative_summary()` but returns a dict instead of a display string.

#### 3. Tests

- **Apply test:** YAML with `type: relative` filter creates the correct filter JSON structure.
- **Round-trip test:** Export a page with a relative date filter, re-apply the exported YAML, verify the filter is recreated identically.
- **Validation tests:** Missing operator, invalid unit, non-positive count, `InThis` with time units, non-column field type all produce errors.
- **Time unit test:** `Minutes`/`Hours` route to `add_relative_time_filter`.
- **InThis auto-correction test:** `InThis` with `count: 5` silently uses `count: 1`.
- **includeToday false round-trip test:** Export with `includeToday: false`, re-apply, verify preserved.

### Files Modified

| File | Change |
|------|--------|
| `src/pbi/apply/ops.py` | Add `elif "relative"` branch in `apply_filters_spec` |
| `src/pbi/export.py` | Add structured export for RelativeDate/RelativeTime filters |
| `src/pbi/filters/parsing.py` | Add `_extract_relative_structured()` helper |
| `tests/test_apply_filters.py` (new or extend) | Apply + round-trip + validation tests |

---

## Feature 2: Field Parameters (Model Command)

### Problem

Field parameters let report consumers switch which measure or dimension a visual displays via a slicer. They are a specific pattern: a calculated table with a known DAX structure, specific column annotations (`PBI_ChangedProperties`), and an `isParameterType` flag. Agents can theoretically create them via `model table create` with raw DAX, but:

1. The DAX pattern is complex and error-prone to type by hand.
2. The required annotations and column metadata are not scaffolded.
3. Without the annotations, Power BI Desktop won't recognize the table as a field parameter.

### Command Syntax

```bash
# Create a measure field parameter
pbi model field-parameter create "Metric Selector" \
  --fields Sales.Revenue Sales.Margin Sales.Orders \
  --labels "Revenue" "Margin" "Orders"

# Create a column/dimension field parameter
pbi model field-parameter create "Dimension Selector" \
  --fields Date.Year Products.Category Geography.Region
```

**Flags:**
- `--fields` (required): Space-separated `Table.Field` references. The command auto-detects whether each is a measure or column.
- `--labels` (optional): Display names for each field. Defaults to the field's property name (e.g., `Revenue` from `Sales.Revenue`).
- `--dry-run`: Preview the TMDL that would be written.
- `-p, --project`: Standard project path.

### Generated TMDL Structure

For `pbi model field-parameter create "Metric Selector" --fields Sales.Revenue Sales.Margin`:

```tmdl
table 'Metric Selector'
	isParameterType
	lineageTag: <uuid>

	column 'Metric Selector'
		dataType: string
		isHidden
		isNameInferred
		lineageTag: <uuid>
		sourceColumn: [Name]
		sortByColumn: 'Metric Selector Order'

		annotation SummarizationType = None

	column 'Metric Selector Fields'
		dataType: string
		isHidden
		lineageTag: <uuid>
		sourceColumn: [Value]

		annotation SummarizationType = None

		annotation PBI_ChangedProperties = ["IsHidden"]

	column 'Metric Selector Order'
		dataType: int64
		isHidden
		lineageTag: <uuid>
		sourceColumn: [Ordinal]

		annotation SummarizationType = None

		annotation PBI_ChangedProperties = ["IsHidden"]

	partition 'Metric Selector' = calculated
		mode: import
		source =
			{
				("Revenue", NAMEOF('Sales'[Revenue]), 0),
				("Margin", NAMEOF('Sales'[Margin]), 1)
			}
```

Key structural elements:
- **`isParameterType`** flag on the table — tells PBI Desktop this is a field parameter.
- **Three columns:** Name (display label, sort-by-order), Fields (the `NAMEOF` values), Order (ordinal for slicer ordering).
- **`PBI_ChangedProperties`** annotations on hidden columns.
- **DAX expression:** A table constructor with `(label, NAMEOF(Table[Field]), ordinal)` tuples.
- **`SummarizationType = None`** on all columns (prevents aggregation in visuals).

### Implementation

#### 1. `src/pbi/modeling/writes_field_parameters.py` (new file)

```python
def create_field_parameter(
    project_root: Path,
    parameter_name: str,
    fields: list[str],           # ["Sales.Revenue", "Sales.Margin"]
    labels: list[str] | None,    # ["Revenue", "Margin"] or None (auto from field name)
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, Path, bool]:
    """Create a field parameter table with the correct TMDL structure."""
```

Steps:
1. Validate `parameter_name` (reuse `validate_table_name`).
2. Check table doesn't already exist.
3. Resolve each field reference against the semantic model to get `(table, field, field_type)`. Verify each field exists.
4. Auto-generate labels from field property names if not provided.
5. Build the DAX expression: `{("Label", NAMEOF('Table'[Field]), 0), ...}`.
6. Build the full TMDL with `isParameterType`, three columns, annotations, partition.
7. Write to `tables/<name>.tmdl`.

#### 2. `src/pbi/commands/model/field_parameters.py` (new file)

CLI command registration:

```python
@model_field_parameter_app.command("create")
def create_field_parameter_cmd(
    name: str,
    fields: list[str],
    labels: list[str] | None = None,
    dry_run: bool = False,
    project: Path = ProjectOpt,
):
```

Output on success:
```
Created field parameter "Metric Selector" with 3 fields
  Revenue      -> Sales.Revenue (measure)
  Margin       -> Sales.Margin (measure)
  Orders       -> Sales.Orders (measure)

Bind to a slicer: pbi visual bind "Page" slicer Values "Metric Selector.Metric Selector"
```

#### 3. `src/pbi/commands/model/base.py`

Register the new subgroup:
```python
model_field_parameter_app = typer.Typer(help="Field parameter operations.", no_args_is_help=True)
model_app.add_typer(model_field_parameter_app, name="field-parameter")
```

#### 4. Model Apply YAML Support

Add a `fieldParameters:` section to the model apply engine:

```yaml
fieldParameters:
  Metric Selector:
    fields:
    - field: Sales.Revenue
      label: Revenue
    - field: Sales.Margin
      label: Margin
    - field: Sales.Orders
      label: Orders
```

The apply handler calls `create_field_parameter()` if the table doesn't exist. If it does exist and has `isParameterType`, it could update the DAX expression (delete + recreate pattern, same as hierarchies).

#### 5. Model Export YAML Support

Detect field parameter tables (has `isParameterType` in TMDL) and export them under the `fieldParameters:` section instead of as raw calculated tables.

#### 6. Tests

- **Create test:** Verify generated TMDL has correct structure, annotations, DAX.
- **Field resolution test:** Mix of measures and columns resolves correctly.
- **Label auto-generation test:** No `--labels` → uses field property names.
- **Duplicate table test:** Error when table already exists.
- **Dry-run test:** No files written.
- **Model apply round-trip:** Export → apply recreates identical structure.

### Implementation Notes

**Parser changes:** The TMDL parser (`parser.py`) does not currently handle bare flags at indent 1. Add handling for `isParameterType` at indent 1 (similar to how `isHidden` is handled at indent 2 for columns). The `SemanticTable` dataclass in `schema.py` needs an `is_parameter_type: bool = False` field to carry this flag.

**DAX quoting:** The `NAMEOF` DAX expression uses a different quoting convention than TMDL identifiers. Table names are always single-quoted in DAX, column names are always bracketed: `NAMEOF('Table Name'[Column])`. The TMDL builder uses `_format_tmdl_name()` for TMDL identifiers, but the DAX expression builder needs its own quoting helper (e.g., `_format_dax_nameof_ref(table, column)`).

**Labels validation:** When `--labels` is provided, validate `len(labels) == len(fields)`. Error if mismatched.

**Model export exclusion:** Tables detected as field parameters should be excluded from the generic `columns` and `partitions` export sections to avoid double-representation.

**Model apply `known_keys`:** Add `"fieldParameters"` to the `known_keys` set in the model apply engine so YAML files with only a `fieldParameters` section are accepted.

**Engineering rule:** The TMDL structure for field parameters is well-documented by Microsoft and follows a rigid pattern. The implementation should be validated by creating a field parameter in PBI Desktop, exporting as PBIP, and comparing the generated TMDL against the canonical export. This validation step is part of the test plan.

### Files Modified/Created

| File | Change |
|------|--------|
| `src/pbi/modeling/writes_field_parameters.py` | New: `create_field_parameter()` + DAX quoting helper |
| `src/pbi/modeling/schema.py` | Add `is_parameter_type: bool = False` to `SemanticTable` |
| `src/pbi/modeling/parser.py` | Parse `isParameterType` flag at indent 1, pass to `SemanticTable` |
| `src/pbi/modeling/__init__.py` | Export new function |
| `src/pbi/commands/model/field_parameters.py` | New: CLI command |
| `src/pbi/commands/model/base.py` | Register `field-parameter` subgroup |
| `src/pbi/model_export.py` | Detect field parameters, export under `fieldParameters:`, exclude from generic sections |
| `src/pbi/modeling/model_apply.py` or equivalent | Handle `fieldParameters:` section, add to `known_keys` |
| `tests/test_field_parameters.py` | New: create + round-trip + validation + labels mismatch tests |

---

## Scope Exclusions

- **Analytics lines (reference/trend/forecast):** Deferred until a PBIR fixture with reference lines is available. The engineering rule requires a canonical exported sample before building write paths.
- **Field parameter binding-side awareness:** The visual bind system doesn't need changes. Once the calculated table exists with correct annotations, agents bind the Name column to a slicer using existing commands.
- **Field parameter deletion/editing:** Not in initial scope. Agents can use `model table delete` if needed.

## Implementation Order

1. **Feature 1 (relative filters in apply)** — smallest change, immediate value, no new files needed beyond tests.
2. **Feature 2 (field parameters)** — new command + TMDL generation + model apply/export integration.
