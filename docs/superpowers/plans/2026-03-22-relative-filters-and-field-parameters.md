# Relative Date Filters in YAML Apply + Field Parameters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire relative date/time filters into the YAML apply engine for round-trip support, and add a `pbi model field-parameter create` command that scaffolds Power BI field parameter tables.

**Architecture:** Feature 1 adds an `elif "relative"` branch in `apply/ops.py` that delegates to existing filter builders, plus a structured export helper for clean round-trip. Feature 2 adds a new TMDL generator (`writes_field_parameters.py`) that produces the `isParameterType` table structure, with CLI command, model apply, and model export integration.

**Tech Stack:** Python 3.11+, Typer CLI, PyYAML, unittest

**Spec:** `docs/superpowers/specs/2026-03-22-relative-filters-and-field-parameters-design.md`

---

## File Map

### Feature 1: Relative Date Filters in Apply

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pbi/apply/ops.py` | Modify (line ~203) | Add `elif "relative"` branch in `apply_filters_spec` |
| `src/pbi/filters/parsing.py` | Modify (after line ~378) | Add `_extract_relative_structured()` helper |
| `src/pbi/export.py` | Modify (line ~294) | Enrich export for RelativeDate/RelativeTime with structured fields |
| `tests/test_relative_filters_apply.py` | Create | Apply, round-trip, validation, edge case tests |

### Feature 2: Field Parameters

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pbi/modeling/schema.py` | Modify (line ~69) | Add `is_parameter_type: bool = False` to `SemanticTable` |
| `src/pbi/modeling/parser.py` | Modify (line ~186) | Parse `isParameterType` bare flag at indent 1 |
| `src/pbi/modeling/writes_field_parameters.py` | Create | `create_field_parameter()` + DAX `NAMEOF` quoting |
| `src/pbi/modeling/__init__.py` | Modify | Re-export `create_field_parameter` |
| `src/pbi/commands/model/field_parameters.py` | Create | CLI `pbi model field-parameter create` command |
| `src/pbi/commands/model/base.py` | Modify (line ~22) | Register `model_field_parameter_app` |
| `src/pbi/model_apply.py` | Modify (line ~214) | Add `fieldParameters` to `known_keys`, add handler |
| `src/pbi/model_export.py` | Modify (line ~34) | Detect and export field parameter tables, exclude from generic sections |
| `tests/test_field_parameters.py` | Create | Create, parse, apply, export, validation tests |

---

## Task 1: Relative Date Filter — Apply Engine Wiring

**Files:**
- Modify: `src/pbi/apply/ops.py:203` (insert before the `else` branch)
- Test: `tests/test_relative_filters_apply.py` (create)

- [ ] **Step 1: Write the failing test for basic relative date filter apply**

Create `tests/test_relative_filters_apply.py`:

```python
"""Tests for relative date/time filter support in the YAML apply engine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.project import Project


def _make_project(root: Path) -> Project:
    from pbi.schema_refs import REPORT_SCHEMA

    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}, "layoutOptimization": "None"}) + "\n",
        encoding="utf-8",
    )
    return Project(root)


class RelativeDateFilterApplyTests(unittest.TestCase):
    def test_apply_relative_date_filter_inlast(self) -> None:
        """Applying type: relative with InLast creates a RelativeDate filter."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Date.OrderDate",
                            "type": "relative",
                            "operator": "InLast",
                            "count": 30,
                            "unit": "Days",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

            # Verify the filter was written correctly
            visuals = project.get_visuals(page)
            visual = visuals[0]
            filters = visual.data.get("filterConfig", {}).get("filters", [])
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["type"], "RelativeDate")

    def test_apply_relative_time_filter(self) -> None:
        """Time units (Minutes/Hours) route to RelativeTime filter."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Events.Timestamp",
                            "type": "relative",
                            "operator": "InLast",
                            "count": 15,
                            "unit": "Minutes",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

    def test_apply_relative_filter_invalid_operator(self) -> None:
        """Invalid operator produces an error, not a crash."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Date.OrderDate",
                            "type": "relative",
                            "operator": "BadOp",
                            "count": 7,
                            "unit": "Days",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertTrue(any("operator" in e for e in result.errors))
            self.assertEqual(result.filters_added, 0)

    def test_apply_relative_filter_invalid_unit(self) -> None:
        """Invalid unit produces an error."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Date.OrderDate",
                            "type": "relative",
                            "operator": "InLast",
                            "count": 7,
                            "unit": "Fortnights",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertTrue(any("unit" in e.lower() for e in result.errors))

    def test_apply_relative_filter_inthis_rejects_time_units(self) -> None:
        """InThis is not valid for Minutes/Hours."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Events.Timestamp",
                            "type": "relative",
                            "operator": "InThis",
                            "count": 1,
                            "unit": "Minutes",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertTrue(any("operator" in e for e in result.errors))

    def test_apply_relative_filter_inthis_autocorrects_count(self) -> None:
        """InThis with count != 1 silently uses count=1."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")

            yaml_content = yaml.safe_dump({
                "pages": [{
                    "name": "Demo",
                    "visuals": [{
                        "name": "chart1",
                        "type": "clusteredColumnChart",
                        "filters": [{
                            "field": "Date.OrderDate",
                            "type": "relative",
                            "operator": "InThis",
                            "count": 5,
                            "unit": "Months",
                        }],
                    }],
                }],
            }, sort_keys=False)

            result = apply_yaml(project, yaml_content)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.filters_added, 1)

    def test_apply_relative_filter_nonpositive_count(self) -> None:
        """Non-positive count produces an error."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            project.create_page("Demo")

            for bad_count in [0, -3]:
                yaml_content = yaml.safe_dump({
                    "pages": [{
                        "name": "Demo",
                        "visuals": [{
                            "name": "chart1",
                            "type": "clusteredColumnChart",
                            "filters": [{
                                "field": "Date.OrderDate",
                                "type": "relative",
                                "operator": "InLast",
                                "count": bad_count,
                                "unit": "Days",
                            }],
                        }],
                    }],
                }, sort_keys=False)

                result = apply_yaml(project, yaml_content)
                self.assertTrue(any("count" in e for e in result.errors), f"Expected error for count={bad_count}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relative_filters_apply.py -v`
Expected: Tests fail with "filter type 'relative' not yet supported in apply" warnings (filters_added stays 0).

- [ ] **Step 3: Implement the relative filter branch in apply_filters_spec**

In `src/pbi/apply/ops.py`, replace the `else:` block at line 203 with the new `elif` + `else`:

```python
        elif filter_type.lower() == "relative":
            from pbi.filters import add_relative_date_filter, add_relative_time_filter

            rel_operator = filter_spec.get("operator", "")
            rel_count = filter_spec.get("count")
            rel_unit = filter_spec.get("unit", "")
            include_today = filter_spec.get("includeToday", True)

            time_units = {"Minutes", "Hours"}
            date_units = {"Days", "Weeks", "CalendarWeeks", "Months", "CalendarMonths", "Years", "CalendarYears"}
            all_units = time_units | date_units
            is_time = rel_unit in time_units

            valid_ops = {"InLast", "InNext"} if is_time else {"InLast", "InThis", "InNext"}
            if rel_operator not in valid_ops:
                result.errors.append(
                    f"{context}: relative filter operator must be one of: {', '.join(sorted(valid_ops))}."
                )
                continue

            if not rel_count or int(rel_count) <= 0:
                result.errors.append(f"{context}: relative filter requires a positive 'count'.")
                continue

            if rel_operator == "InThis":
                rel_count = 1

            if rel_unit not in all_units:
                result.errors.append(
                    f"{context}: relative filter unit '{rel_unit}' not recognized. "
                    f"Use one of: {', '.join(sorted(all_units))}."
                )
                continue

            field_type_name = "column"
            if project is not None:
                entity, prop, field_type_name, _ = resolve_apply_field(
                    field_ref, project, session=session,
                )

            if field_type_name != "column":
                result.errors.append(
                    f"{context}: relative filters only support column fields, not {field_type_name}."
                )
                continue

            try:
                if is_time:
                    add_relative_time_filter(
                        data, entity, prop,
                        operator=rel_operator,
                        time_units_count=int(rel_count),
                        time_unit_type=rel_unit,
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                else:
                    add_relative_date_filter(
                        data, entity, prop,
                        operator=rel_operator,
                        time_units_count=int(rel_count),
                        time_unit_type=rel_unit,
                        include_today=bool(include_today),
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                result.filters_added += 1
            except (ValueError, NotImplementedError) as e:
                result.errors.append(f"{context}: {e}")
        else:
            result.warnings.append(
                f"{context}: filter type '{filter_type}' not yet supported in apply."
            )
```

Key: the existing `else:` at line 203 becomes the final `else:` after this new `elif`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relative_filters_apply.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 6: Commit**

```bash
git add src/pbi/apply/ops.py tests/test_relative_filters_apply.py
git commit -m "feat: support type: relative filters in YAML apply engine"
```

---

## Task 2: Relative Date Filter — Structured Export for Round-Trip

**Files:**
- Modify: `src/pbi/filters/parsing.py` (after line ~378)
- Modify: `src/pbi/export.py` (in `_export_filters`, line ~294)
- Test: `tests/test_relative_filters_apply.py` (extend)

- [ ] **Step 1: Write the failing round-trip test**

Add to `tests/test_relative_filters_apply.py`:

```python
from pbi.export import export_yaml


class RelativeDateFilterExportTests(unittest.TestCase):
    def test_export_relative_date_produces_structured_yaml(self) -> None:
        """Exported RelativeDate filter has operator/count/unit, not just raw."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart", name="chart1")

            from pbi.filters import add_relative_date_filter
            add_relative_date_filter(
                visual.data, "Date", "OrderDate",
                operator="InLast", time_units_count=30, time_unit_type="Days",
                include_today=True,
            )
            project.save_visual(page, visual)

            exported = yaml.safe_load(export_yaml(project))
            vis_spec = exported["pages"][0]["visuals"][0]
            filters = vis_spec.get("filters", [])
            self.assertEqual(len(filters), 1)
            f = filters[0]
            self.assertEqual(f["type"], "relative")
            self.assertEqual(f["operator"], "InLast")
            self.assertEqual(f["count"], 30)
            self.assertEqual(f["unit"], "Days")
            self.assertNotIn("raw", f)

    def test_roundtrip_relative_date_filter(self) -> None:
        """Export a relative filter, re-apply, verify filter exists."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart", name="chart1")

            from pbi.filters import add_relative_date_filter
            add_relative_date_filter(
                visual.data, "Date", "OrderDate",
                operator="InLast", time_units_count=7, time_unit_type="Days",
                include_today=False,
            )
            project.save_visual(page, visual)

            exported_yaml = export_yaml(project)
            exported = yaml.safe_load(exported_yaml)

            # Verify includeToday: false is preserved
            f = exported["pages"][0]["visuals"][0]["filters"][0]
            self.assertEqual(f.get("includeToday"), False)

            # Re-apply to a fresh project
            root2 = Path(tmp) / "project2"
            root2.mkdir()
            project2 = _make_project(root2)
            result = apply_yaml(project2, exported_yaml)
            self.assertEqual(result.errors, [])
            self.assertGreaterEqual(result.filters_added, 1)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `python -m pytest tests/test_relative_filters_apply.py::RelativeDateFilterExportTests -v`
Expected: FAIL — exported filter has `type: RelativeDate` not `type: relative`, and includes `raw:`.

- [ ] **Step 3: Add `_extract_relative_structured()` to parsing.py**

Add after `_match_relative_date_between` (after line ~378) in `src/pbi/filters/parsing.py`:

```python
def _extract_relative_structured(filter_obj: dict) -> dict | None:
    """Extract structured {operator, count, unit, includeToday} from a relative filter.

    Returns a dict suitable for YAML export, or None if the structure is unrecognized.
    """
    filter_type = filter_obj.get("type")
    where = filter_obj.get("filter", {}).get("Where", [])
    if not where:
        return None
    condition = where[0].get("Condition", {})

    if filter_type == "RelativeDate":
        # InThis pattern: Comparison with DateSpan(Now(), unit)
        comparison = condition.get("Comparison")
        if comparison and comparison.get("ComparisonKind") == 0:
            right = comparison.get("Right", {})
            span = right.get("DateSpan", {})
            if _is_now_expr(span.get("Expression", {})):
                unit_name = _time_unit_name(span.get("TimeUnit"))
                if unit_name:
                    return {"operator": "InThis", "count": 1, "unit": unit_name}

        # InLast/InNext pattern: Between with DateAdd offsets
        between = condition.get("Between")
        if between:
            lower = between.get("LowerBound", {})
            upper = between.get("UpperBound", {})
            result = _match_relative_date_structured(lower, upper)
            if result:
                return result

    if filter_type == "RelativeTime":
        between = condition.get("Between")
        if between:
            lower_bound = between.get("LowerBound", {})
            upper_bound = between.get("UpperBound", {})
            if _is_now_expr(upper_bound):
                parsed = _parse_date_add(lower_bound)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] < 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return {"operator": "InLast", "count": abs(parsed[1]), "unit": unit_name}
            if _is_now_expr(lower_bound):
                parsed = _parse_date_add(upper_bound)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] > 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return {"operator": "InNext", "count": parsed[1], "unit": unit_name}

    return None


def _match_relative_date_structured(lower: dict, upper: dict) -> dict | None:
    """Extract structured fields from a RelativeDate Between condition."""
    lower_span = lower.get("DateSpan", {})
    upper_span = upper.get("DateSpan", {})
    lower_expr = lower_span.get("Expression", {}) if lower_span else lower
    upper_expr = upper_span.get("Expression", {}) if upper_span else upper
    lower_span_unit = lower_span.get("TimeUnit") if lower_span else None
    upper_span_unit = upper_span.get("TimeUnit") if upper_span else None

    # InLast with includeToday: DateAdd(DateAdd(Now(), 1, Days), -N, Unit) .. Now()
    if (
        lower_span_unit == DATE_UNIT_CODES["Days"]
        and upper_span_unit == DATE_UNIT_CODES["Days"]
        and _is_now_expr(upper_expr)
    ):
        first = _parse_date_add(lower_expr)
        if first and first[1] < 0:
            second = _parse_date_add(first[0])
            if second and _is_now_expr(second[0]) and second[1] == 1 and second[2] == DATE_UNIT_CODES["Days"]:
                unit_name = _time_unit_name(first[2])
                if unit_name:
                    return {"operator": "InLast", "count": abs(first[1]), "unit": unit_name, "includeToday": True}

    # InNext with includeToday: Now() .. DateAdd(DateAdd(Now(), -1, Days), N, Unit)
    if (
        lower_span_unit == DATE_UNIT_CODES["Days"]
        and upper_span_unit == DATE_UNIT_CODES["Days"]
        and _is_now_expr(lower_expr)
    ):
        first = _parse_date_add(upper_expr)
        if first and first[1] > 0:
            second = _parse_date_add(first[0])
            if second and _is_now_expr(second[0]) and second[1] == -1 and second[2] == DATE_UNIT_CODES["Days"]:
                unit_name = _time_unit_name(first[2])
                if unit_name:
                    return {"operator": "InNext", "count": first[1], "unit": unit_name, "includeToday": True}

    # InLast without includeToday: DateAdd(Now(), -N, Unit) .. DateAdd(Now(), -1, Unit)
    lower_add = _parse_date_add(lower_expr)
    upper_add = _parse_date_add(upper_expr)
    if lower_add and upper_add:
        if (
            _is_now_expr(lower_add[0])
            and _is_now_expr(upper_add[0])
            and lower_add[2] == upper_add[2] == lower_span_unit == upper_span_unit
        ):
            unit_name = _time_unit_name(lower_add[2])
            if unit_name:
                if lower_add[1] < 0 and upper_add[1] == -1:
                    return {"operator": "InLast", "count": abs(lower_add[1]), "unit": unit_name, "includeToday": False}
                if lower_add[1] == 1 and upper_add[1] > 0:
                    return {"operator": "InNext", "count": upper_add[1], "unit": unit_name, "includeToday": False}

    return None
```

Also add `_extract_relative_structured` and `_match_relative_date_structured` to the module imports in `src/pbi/filters/__init__.py`.

- [ ] **Step 4: Enrich `_export_filters` in export.py**

In `src/pbi/export.py`, after building the `entry` dict (around line 318), add:

```python
        if info.filter_type in ("RelativeDate", "RelativeTime"):
            from pbi.filters.parsing import _extract_relative_structured

            structured = _extract_relative_structured(f)
            if structured:
                entry["type"] = "relative"
                entry.update(structured)
                entry.pop("raw", None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_relative_filters_apply.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pbi/filters/parsing.py src/pbi/filters/__init__.py src/pbi/export.py tests/test_relative_filters_apply.py
git commit -m "feat: structured export for relative date/time filters (round-trip)"
```

---

## Task 3: Field Parameter — Parser and Schema Changes

**Files:**
- Modify: `src/pbi/modeling/schema.py:69` (add field to `SemanticTable`)
- Modify: `src/pbi/modeling/parser.py:186` (parse `isParameterType` flag)
- Test: `tests/test_field_parameters.py` (create)

- [ ] **Step 1: Write the failing test for parsing isParameterType**

Create `tests/test_field_parameters.py`:

```python
"""Tests for field parameter support."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pbi.model import SemanticModel


def _make_project(root: Path) -> None:
    from pbi.schema_refs import REPORT_SCHEMA

    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}, "layoutOptimization": "None"}) + "\n",
        encoding="utf-8",
    )


def _write_table(root: Path, filename: str, content: str) -> Path:
    tables = root / "Sample.SemanticModel" / "definition" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / filename
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class FieldParameterParserTests(unittest.TestCase):
    def test_parse_is_parameter_type_flag(self) -> None:
        """Parser detects isParameterType on a table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Metric_Selector.tmdl", """
table 'Metric Selector'
\tisParameterType
\tlineageTag: abc-123

\tcolumn 'Metric Selector'
\t\tdataType: string
\t\tlineageTag: col-1
\t\tsourceColumn: [Name]

\tpartition 'Metric Selector' = calculated
\t\tmode: import
\t\tsource = {("Revenue", NAMEOF('Sales'[Revenue]), 0)}
""")
            model = SemanticModel.load(root)
            table = model.find_table("Metric Selector")
            self.assertTrue(table.is_parameter_type)

    def test_regular_table_not_parameter_type(self) -> None:
        """Normal tables have is_parameter_type=False."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: xyz-456

\tcolumn Revenue
\t\tdataType: decimal
\t\tlineageTag: col-2
""")
            model = SemanticModel.load(root)
            table = model.find_table("Sales")
            self.assertFalse(table.is_parameter_type)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_field_parameters.py::FieldParameterParserTests -v`
Expected: FAIL — `SemanticTable` has no `is_parameter_type` attribute.

- [ ] **Step 3: Add `is_parameter_type` to SemanticTable**

In `src/pbi/modeling/schema.py`, add after line 76 (`data_category: str = ""`):

```python
    is_parameter_type: bool = False
```

- [ ] **Step 4: Parse `isParameterType` in the TMDL parser**

In `src/pbi/modeling/parser.py`, inside the `if indent == 1:` block (around line 186), add before the `if stripped.startswith("column ")` check:

```python
            if stripped == "isParameterType":
                table_props["isParameterType"] = "true"
                continue
```

Then in the `_flush()` or table construction logic where `SemanticTable` is built, pass the flag. Find where `data_category` is assigned from `table_props` and add alongside it:

```python
is_parameter_type="isParameterType" in table_props,
```

Note: Check the exact location where `SemanticTable(...)` is constructed in the parser — the `table_props` dict is used to pass `data_category`. Follow the same pattern.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_field_parameters.py::FieldParameterParserTests -v`
Expected: Both tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pbi/modeling/schema.py src/pbi/modeling/parser.py tests/test_field_parameters.py
git commit -m "feat: parse isParameterType flag from TMDL tables"
```

---

## Task 4: Field Parameter — TMDL Generator

**Files:**
- Create: `src/pbi/modeling/writes_field_parameters.py`
- Modify: `src/pbi/modeling/__init__.py` (add re-export)
- Test: `tests/test_field_parameters.py` (extend)

- [ ] **Step 1: Write the failing test for create_field_parameter**

Add to `tests/test_field_parameters.py`:

```python
from pbi.model import SemanticModel, create_field_parameter


class FieldParameterCreateTests(unittest.TestCase):
    def test_create_field_parameter_basic(self) -> None:
        """Create a field parameter table with measures."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            name, path, created = create_field_parameter(
                root, "Metric Selector",
                fields=["Sales.Revenue", "Sales.Margin"],
                labels=["Revenue", "Margin"],
            )
            self.assertTrue(created)
            self.assertTrue(path.exists())

            # Verify the TMDL has isParameterType
            content = path.read_text(encoding="utf-8")
            self.assertIn("isParameterType", content)

            # Verify three columns exist
            self.assertIn("sourceColumn: [Name]", content)
            self.assertIn("sourceColumn: [Value]", content)
            self.assertIn("sourceColumn: [Ordinal]", content)

            # Verify DAX NAMEOF references
            self.assertIn("NAMEOF('Sales'[Revenue])", content)
            self.assertIn("NAMEOF('Sales'[Margin])", content)

            # Verify it parses back correctly
            model = SemanticModel.load(root)
            table = model.find_table("Metric Selector")
            self.assertTrue(table.is_parameter_type)

    def test_create_field_parameter_auto_labels(self) -> None:
        """Labels default to field property names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            _, path, _ = create_field_parameter(
                root, "Selector",
                fields=["Sales.Revenue"],
                labels=None,
            )
            content = path.read_text(encoding="utf-8")
            self.assertIn('"Revenue"', content)

    def test_create_field_parameter_labels_length_mismatch(self) -> None:
        """Mismatched labels and fields raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            with self.assertRaises(ValueError):
                create_field_parameter(
                    root, "Selector",
                    fields=["Sales.Revenue", "Sales.Margin"],
                    labels=["Revenue"],  # only 1 label for 2 fields
                )

    def test_create_field_parameter_duplicate_table(self) -> None:
        """Error when table already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            create_field_parameter(root, "Selector", fields=["Sales.Revenue"], labels=None)
            with self.assertRaises(ValueError):
                create_field_parameter(root, "Selector", fields=["Sales.Revenue"], labels=None)

    def test_create_field_parameter_dry_run(self) -> None:
        """Dry run doesn't write files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            _, path, _ = create_field_parameter(
                root, "Selector",
                fields=["Sales.Revenue"],
                labels=None,
                dry_run=True,
            )
            self.assertFalse(path.exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_field_parameters.py::FieldParameterCreateTests -v`
Expected: FAIL — `create_field_parameter` does not exist.

- [ ] **Step 3: Implement `writes_field_parameters.py`**

Create `src/pbi/modeling/writes_field_parameters.py`:

```python
"""Field parameter table creation for Power BI semantic models."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .schema import SemanticModel
from .writes import _format_tmdl_name, _write_tmdl_lines, validate_table_name


def _format_dax_field_ref(table: str, field: str) -> str:
    """Format a DAX NAMEOF reference: NAMEOF('Table'[Field])."""
    escaped_table = table.replace("'", "''")
    return f"NAMEOF('{escaped_table}'[{field}])"


def create_field_parameter(
    project_root: Path,
    parameter_name: str,
    fields: list[str],
    labels: list[str] | None,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, Path, bool]:
    """Create a field parameter table with the correct TMDL structure.

    Returns (table_name, tmdl_path, created).
    """
    validate_table_name(parameter_name)

    if not fields:
        raise ValueError("At least one field is required.")

    if labels is not None and len(labels) != len(fields):
        raise ValueError(
            f"Labels count ({len(labels)}) must match fields count ({len(fields)})."
        )

    loaded_model = model or SemanticModel.load(project_root)

    # Check duplicate
    for t in loaded_model.tables:
        if t.name.lower() == parameter_name.lower():
            raise ValueError(f'Table "{t.name}" already exists.')

    # Resolve fields and auto-generate labels
    resolved: list[tuple[str, str, str]] = []  # (label, table, field)
    for i, field_ref in enumerate(fields):
        dot = field_ref.find(".")
        if dot == -1:
            raise ValueError(f"Field must be Table.Field format: {field_ref}")
        table_name = field_ref[:dot]
        field_name = field_ref[dot + 1:]

        # Validate field exists
        try:
            sem_table = loaded_model.find_table(table_name)
        except ValueError as e:
            raise ValueError(f"Field parameter: {e}") from e

        field_found = False
        for col in sem_table.columns:
            if col.name.lower() == field_name.lower():
                field_found = True
                field_name = col.name  # canonical case
                table_name = sem_table.name
                break
        if not field_found:
            for meas in sem_table.measures:
                if meas.name.lower() == field_name.lower():
                    field_found = True
                    field_name = meas.name
                    table_name = sem_table.name
                    break
        if not field_found:
            raise ValueError(f'Field "{field_ref}" not found in model.')

        label = labels[i] if labels else field_name
        resolved.append((label, table_name, field_name))

    # Build TMDL
    tmdl_name = _format_tmdl_name(parameter_name)
    lines: list[str] = [
        f"table {tmdl_name}",
        "\tisParameterType",
        f"\tlineageTag: {uuid.uuid4()}",
        "",
    ]

    # Name column (display label, sorted by order)
    order_col_name = _format_tmdl_name(f"{parameter_name} Order")
    lines.extend([
        f"\tcolumn {tmdl_name}",
        "\t\tdataType: string",
        "\t\tisHidden",
        "\t\tisNameInferred",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Name]",
        f"\t\tsortByColumn: {order_col_name}",
        "",
        "\t\tannotation SummarizationType = None",
        "",
    ])

    # Fields column (NAMEOF values)
    fields_col_name = _format_tmdl_name(f"{parameter_name} Fields")
    lines.extend([
        f"\tcolumn {fields_col_name}",
        "\t\tdataType: string",
        "\t\tisHidden",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Value]",
        "",
        "\t\tannotation SummarizationType = None",
        "",
        '\t\tannotation PBI_ChangedProperties = ["IsHidden"]',
        "",
    ])

    # Order column (ordinal)
    lines.extend([
        f"\tcolumn {order_col_name}",
        "\t\tdataType: int64",
        "\t\tisHidden",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Ordinal]",
        "",
        "\t\tannotation SummarizationType = None",
        "",
        '\t\tannotation PBI_ChangedProperties = ["IsHidden"]',
        "",
    ])

    # DAX table constructor
    dax_rows = []
    for i, (label, table, field) in enumerate(resolved):
        escaped_label = label.replace('"', '""')
        nameof = _format_dax_field_ref(table, field)
        dax_rows.append(f'("{escaped_label}", {nameof}, {i})')

    partition_name = _format_tmdl_name(parameter_name)
    lines.append(f"\tpartition {partition_name} = calculated")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t{")
    for i, row in enumerate(dax_rows):
        suffix = "," if i < len(dax_rows) - 1 else ""
        lines.append(f"\t\t\t{row}{suffix}")
    lines.append("\t\t\t}")
    lines.append("")

    # Write
    tables_dir = loaded_model.folder / "definition" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = parameter_name.replace(" ", "_").replace("'", "")
    tmdl_path = tables_dir / f"{safe_filename}.tmdl"

    if not dry_run:
        _write_tmdl_lines(tmdl_path, lines)

    return parameter_name, tmdl_path, True
```

- [ ] **Step 4: Add re-export in `__init__.py`**

In `src/pbi/modeling/__init__.py`, add the import:

```python
from .writes_field_parameters import create_field_parameter
```

And add `"create_field_parameter"` to the `__all__` list.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_field_parameters.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pbi/modeling/writes_field_parameters.py src/pbi/modeling/__init__.py tests/test_field_parameters.py
git commit -m "feat: create_field_parameter() generates field parameter TMDL"
```

---

## Task 5: Field Parameter — CLI Command

**Files:**
- Create: `src/pbi/commands/model/field_parameters.py`
- Modify: `src/pbi/commands/model/base.py` (register subgroup)
- Test: `tests/test_field_parameters.py` (extend with CLI test)

- [ ] **Step 1: Write the failing CLI test**

Add to `tests/test_field_parameters.py`:

```python
from typer.testing import CliRunner
from pbi.cli import app

runner = CliRunner()


class FieldParameterCLITests(unittest.TestCase):
    def test_cli_create_field_parameter(self) -> None:
        """CLI creates a field parameter table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            result = runner.invoke(app, [
                "model", "field-parameter", "create",
                "Metric Selector",
                "--fields", "Sales.Revenue", "Sales.Margin",
                "--labels", "Revenue", "Margin",
                "-p", str(root),
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Created field parameter", result.output)
            self.assertIn("Revenue", result.output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_field_parameters.py::FieldParameterCLITests -v`
Expected: FAIL — no `field-parameter` subcommand.

- [ ] **Step 3: Register the subgroup in base.py**

In `src/pbi/commands/model/base.py`, add after the existing app definitions (line ~22):

```python
model_field_parameter_app = typer.Typer(help="Field parameter operations.", no_args_is_help=True)
```

And in the registration section (after line ~28):

```python
model_app.add_typer(model_field_parameter_app, name="field-parameter")
```

- [ ] **Step 4: Create the CLI command file**

Create `src/pbi/commands/model/field_parameters.py`:

```python
"""CLI commands for field parameter management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..common import ProjectOpt, console
from .base import get_model, model_field_parameter_app


@model_field_parameter_app.command("create")
def create_field_parameter_cmd(
    name: Annotated[str, typer.Argument(help="Name for the field parameter table.")],
    fields: Annotated[list[str], typer.Option("--fields", help="Table.Field references to include.")],
    labels: Annotated[list[str] | None, typer.Option("--labels", help="Display labels (one per field). Defaults to field names.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    project: Path = ProjectOpt,
) -> None:
    """Create a field parameter table from model fields."""
    from pbi.model import SemanticModel, create_field_parameter

    proj, model = get_model(project)
    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    try:
        param_name, path, created = create_field_parameter(
            proj.root,
            name,
            fields=fields,
            labels=labels,
            dry_run=dry_run,
            model=model,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Resolve display info
    resolved_labels = labels if labels else [f.split(".", 1)[1] if "." in f else f for f in fields]
    resolved_types = []
    for field_ref in fields:
        dot = field_ref.find(".")
        if dot == -1:
            resolved_types.append("field")
            continue
        table_name = field_ref[:dot]
        field_name = field_ref[dot + 1:]
        try:
            sem_table = model.find_table(table_name)
            field_type = "column"
            for m in sem_table.measures:
                if m.name.lower() == field_name.lower():
                    field_type = "measure"
                    break
            resolved_types.append(field_type)
        except ValueError:
            resolved_types.append("field")

    console.print(f'{prefix}Created field parameter "[cyan]{param_name}[/cyan]" with {len(fields)} fields')
    for label, field_ref, ftype in zip(resolved_labels, fields, resolved_types):
        console.print(f"  [cyan]{label:<16}[/cyan] [dim]->[/dim] {field_ref} [dim]({ftype})[/dim]")
    console.print()
    console.print(f'[dim]Bind to a slicer:[/dim] pbi visual bind "Page" slicer Values "{param_name}.{param_name}"')
```

- [ ] **Step 5: Register the command module import and facade re-export**

In `src/pbi/commands/model/__init__.py`, add the import for the new module (following the pattern of other model subcommands):

```python
from . import field_parameters as _field_parameters
```

And add `model_field_parameter_app` to the imports from `.base`.

In `src/pbi/model.py` (the compatibility facade), add the re-export:

```python
from pbi.modeling import create_field_parameter
```

This is required because `model_apply.py` and the CLI command both import from `pbi.model`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_field_parameters.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 8: Commit**

```bash
git add src/pbi/commands/model/field_parameters.py src/pbi/commands/model/base.py src/pbi/commands/model/__init__.py src/pbi/model.py tests/test_field_parameters.py
git commit -m "feat: pbi model field-parameter create CLI command"
```

---

## Task 6: Field Parameter — Model Apply + Export Integration

**Files:**
- Modify: `src/pbi/model_apply.py:214` (add `fieldParameters` to known_keys + handler)
- Modify: `src/pbi/model_export.py:34` (detect and export field parameters, exclude from generic sections)
- Test: `tests/test_field_parameters.py` (extend)

- [ ] **Step 1: Write the failing model apply test**

Add to `tests/test_field_parameters.py`:

```python
import yaml
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml


class FieldParameterApplyExportTests(unittest.TestCase):
    def test_model_apply_creates_field_parameter(self) -> None:
        """fieldParameters section in YAML creates the table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            yaml_content = yaml.safe_dump({
                "fieldParameters": {
                    "Metric Selector": {
                        "fields": [
                            {"field": "Sales.Revenue", "label": "Revenue"},
                            {"field": "Sales.Margin", "label": "Margin"},
                        ],
                    },
                },
            }, sort_keys=False)

            result = apply_model_yaml(root, yaml_content)
            self.assertEqual(result.errors, [], result.errors)

            model = SemanticModel.load(root)
            table = model.find_table("Metric Selector")
            self.assertTrue(table.is_parameter_type)

    def test_model_export_includes_field_parameters(self) -> None:
        """Field parameter tables appear under fieldParameters in export."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            create_field_parameter(
                root, "Metric Selector",
                fields=["Sales.Revenue"],
                labels=["Revenue"],
            )

            exported = yaml.safe_load(export_model_yaml(root))
            self.assertIn("fieldParameters", exported)
            self.assertIn("Metric Selector", exported["fieldParameters"])

            # Should NOT appear in generic columns/partitions sections
            columns = exported.get("columns", {})
            self.assertNotIn("Metric Selector", columns)

    def test_model_apply_rejects_yaml_with_only_unknown_keys(self) -> None:
        """YAML with only fieldParameters is accepted (in known_keys)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            yaml_content = yaml.safe_dump({
                "fieldParameters": {
                    "Selector": {
                        "fields": [{"field": "Sales.Revenue", "label": "Revenue"}],
                    },
                },
            }, sort_keys=False)

            result = apply_model_yaml(root, yaml_content)
            # Should NOT contain "YAML must include at least one of" error
            for err in result.errors:
                self.assertNotIn("must include at least one of", err)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_field_parameters.py::FieldParameterApplyExportTests -v`
Expected: FAIL — `fieldParameters` not in known_keys, no handler, no export logic.

- [ ] **Step 3: Add model apply handler**

In `src/pbi/model_apply.py`:

1. Add `"fieldParameters"` to the `known_keys` set at line 214.

2. Add the handler block (before the `known_keys` check, following the pattern of other sections):

```python
    field_params_spec = spec.get("fieldParameters")
    if field_params_spec is not None:
        _apply_field_parameters(
            project_root,
            field_params_spec,
            result,
            dry_run=dry_run,
            model=model,
        )
```

3. Add `field_parameters_created: list[str]` to `ModelApplyResult` (after `perspectives_updated` at line 63):

```python
    field_parameters_created: list[str] = field(default_factory=list)
```

And add `or self.field_parameters_created` to the `has_changes` property.

4. Add the handler function:

```python
def _apply_field_parameters(
    project_root: Path,
    spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
) -> None:
    """Apply fieldParameters section."""
    if not isinstance(spec, dict):
        result.errors.append("fieldParameters must be a mapping.")
        return

    from pbi.model import create_field_parameter

    for param_name, param_spec in spec.items():
        if not isinstance(param_spec, dict):
            result.errors.append(f'fieldParameters.{param_name}: must be a mapping.')
            continue

        fields_list = param_spec.get("fields", [])
        if not isinstance(fields_list, list) or not fields_list:
            result.errors.append(f'fieldParameters.{param_name}: requires a non-empty "fields" list.')
            continue

        field_refs = []
        labels = []
        for entry in fields_list:
            if isinstance(entry, dict):
                field_refs.append(entry.get("field", ""))
                labels.append(entry.get("label", entry.get("field", "").split(".")[-1]))
            elif isinstance(entry, str):
                field_refs.append(entry)
                labels.append(entry.split(".")[-1])
            else:
                result.errors.append(f'fieldParameters.{param_name}: each field must be a string or mapping.')
                continue

        # Skip if table already exists as a field parameter
        try:
            existing = model.find_table(param_name)
            if existing.is_parameter_type:
                continue
        except ValueError:
            pass  # table doesn't exist — create it

        try:
            create_field_parameter(
                project_root,
                param_name,
                fields=field_refs,
                labels=labels,
                dry_run=dry_run,
                model=model,
            )
            result.field_parameters_created.append(param_name)
        except ValueError as e:
            result.errors.append(f'fieldParameters.{param_name}: {e}')
```

- [ ] **Step 4: Add model export support**

In `src/pbi/model_export.py`, modify `export_model_yaml`:

1. After the tables section (around line 44), add field parameter detection and export:

```python
    # Field parameters
    field_params_section: dict = {}
    field_param_tables: set[str] = set()
    for table in loaded_model.tables:
        if table.is_parameter_type:
            field_param_tables.add(table.name)
            # Extract fields from the partition DAX expression
            fp_fields = _extract_field_parameter_fields(table)
            if fp_fields:
                field_params_section[table.name] = {"fields": fp_fields}
    if field_params_section:
        spec["fieldParameters"] = field_params_section
```

2. In the columns and partitions export loops, skip field parameter tables:

```python
    # In the columns loop:
    for table in loaded_model.tables:
        if table.name in field_param_tables:
            continue
        # ... existing column export ...

    # In the partitions loop (if it exists):
    for table in loaded_model.tables:
        if table.name in field_param_tables:
            continue
        # ... existing partition export ...
```

3. Add the extraction helper:

```python
def _extract_field_parameter_fields(table) -> list[dict]:
    """Extract field references from a field parameter table's partition DAX."""
    import re

    result = []
    for partition in table.partitions:
        if not partition.source_expression:
            continue
        # Match ("Label", NAMEOF('Table'[Field]), ordinal) tuples
        pattern = r'\(\s*"([^"]+)"\s*,\s*NAMEOF\(\'([^\']+)\'\[([^\]]+)\]\)\s*,\s*(\d+)\s*\)'
        for match in re.finditer(pattern, partition.source_expression):
            label, tbl, fld, ordinal = match.groups()
            result.append({"field": f"{tbl}.{fld}", "label": label})
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_field_parameters.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: No regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pbi/model_apply.py src/pbi/model_export.py tests/test_field_parameters.py
git commit -m "feat: field parameter support in model apply and export YAML"
```

---

## Task 7: Documentation Updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/cheatsheet.md`
- Modify: `docs/agent-workflows.md`
- Modify: `src/pbi/capabilities.py`

- [ ] **Step 1: Update CLAUDE.md**

Add to the "YAML Apply Features" section:
- `type: relative` filter with `operator`, `count`, `unit`, `includeToday`

Add to the "Model Commands" section:
- `model field-parameter create <name> --fields Table.Field... [--labels ...]`

Add to the "Model Apply YAML Sections" section:
- **fieldParameters:** name-keyed mapping with `fields` list of `{field, label}`

- [ ] **Step 2: Update docs/cheatsheet.md**

Add relative date filter YAML example to the Filters section.
Add `pbi model field-parameter create` to the Model section.

- [ ] **Step 3: Update docs/agent-workflows.md**

Add field parameter to discovery/model commands section.

- [ ] **Step 4: Update capabilities.py**

Update the Data capability gap text to remove the field-parameter mention.
Add the relative filter apply support to the Filters capability.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/cheatsheet.md docs/agent-workflows.md src/pbi/capabilities.py
git commit -m "docs: add relative filter apply and field parameter documentation"
```
