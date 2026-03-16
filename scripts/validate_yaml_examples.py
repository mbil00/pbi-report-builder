#!/usr/bin/env python3
"""Validate YAML examples against the current application feature set.

Checks that docs/yaml-examples/ covers all supported visual types,
filter modes, conditional formatting modes, and YAML features.
Reports gaps — does not modify any files.

Usage:
    python scripts/validate_yaml_examples.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXAMPLES_DIR = PROJECT_ROOT / "docs" / "yaml-examples"
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Load current application feature sets
# ---------------------------------------------------------------------------

def get_visual_types_with_roles() -> dict[str, list[str]]:
    """Return {visual_type: [role_names]} from roles.py."""
    from pbi.roles import VISUAL_ROLES
    return {
        vtype: [r["name"] for r in roles]
        for vtype, roles in VISUAL_ROLES.items()
    }


def get_visual_type_aliases() -> dict[str, str]:
    """Return {alias: canonical_type} from roles.py."""
    from pbi.roles import VISUAL_TYPE_ALIASES
    return dict(VISUAL_TYPE_ALIASES)


def get_filter_modes() -> set[str]:
    """Return the set of supported filter type strings (lowercase)."""
    return {"categorical", "include", "exclude", "topn", "range"}


def get_cf_modes() -> set[str]:
    """Return the set of supported conditional formatting modes."""
    return {"measure", "gradient", "rules"}


def get_page_yaml_keys() -> set[str]:
    """Return the set of special page-level YAML keys handled by apply."""
    return {
        "name", "width", "height", "displayOption", "visibility",
        "visuals", "filters", "interactions", "bookmarks",
        "type", "pageBinding", "tooltip", "drillthrough",
    }


def get_visual_yaml_keys() -> set[str]:
    """Return the set of special visual-level YAML keys handled by apply."""
    return {
        "id", "name", "type", "position", "size", "bindings", "sort",
        "filters", "conditionalFormatting", "isHidden", "pbir", "style",
        "kpis", "layout", "accentBar", "referenceLabelLayout",
    }


def get_bookmark_fields() -> set[str]:
    """Return the set of bookmark entry fields."""
    return {"name", "page", "hide", "target", "captureData", "captureDisplay", "capturePage"}


def get_interaction_types() -> set[str]:
    """Return the set of interaction type strings."""
    return {"DataFilter", "Highlight", "NoFilter"}


# ---------------------------------------------------------------------------
# Scan example files
# ---------------------------------------------------------------------------

def read_all_examples() -> dict[str, str]:
    """Return {filename: content} for all .yaml files in the examples dir."""
    results = {}
    if not EXAMPLES_DIR.exists():
        return results
    for path in sorted(EXAMPLES_DIR.glob("*.yaml")):
        results[path.name] = path.read_text(encoding="utf-8")
    return results


def find_in_examples(examples: dict[str, str], pattern: str, flags: int = re.IGNORECASE) -> list[tuple[str, str]]:
    """Return [(filename, matched_line)] for lines matching a regex pattern."""
    compiled = re.compile(pattern, flags)
    matches = []
    for filename, content in examples.items():
        for line in content.splitlines():
            if compiled.search(line):
                matches.append((filename, line.strip()))
    return matches


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def _common_visual_types() -> set[str]:
    """Visual types agents commonly use. Niche types are reported separately."""
    return {
        "clusteredBarChart", "clusteredColumnChart", "stackedBarChart",
        "stackedColumnChart", "lineChart", "areaChart",
        "lineClusteredColumnComboChart", "lineStackedColumnComboChart",
        "pieChart", "donutChart", "treemap", "waterfallChart", "funnel",
        "scatterChart", "gauge", "kpi",
        "cardVisual", "multiRowCard",
        "tableEx", "pivotTable",
        "slicer", "advancedSlicerVisual",
        "shape", "textbox", "image", "actionButton",
    }


def check_visual_types(examples: dict[str, str]) -> list[str]:
    """Check that common visual types with roles are demonstrated."""
    gaps = []
    types_with_roles = get_visual_types_with_roles()
    aliases = get_visual_type_aliases()
    all_content = "\n".join(examples.values())
    common = _common_visual_types()

    missing_common = []
    missing_niche = []

    for vtype in sorted(types_with_roles):
        type_found = re.search(rf'\btype:\s*{re.escape(vtype)}\b', all_content, re.IGNORECASE)
        alias_found = any(
            re.search(rf'\btype:\s*{re.escape(alias)}\b', all_content, re.IGNORECASE)
            for alias, canonical in aliases.items()
            if canonical == vtype
        )
        if not type_found and not alias_found:
            roles = types_with_roles[vtype]
            entry = f"Visual type '{vtype}' (roles: {', '.join(roles)})"
            if vtype in common:
                missing_common.append(entry)
            else:
                missing_niche.append(entry)

    for entry in missing_common:
        gaps.append(f"{entry} — not demonstrated")
    if missing_niche:
        gaps.append(f"({len(missing_niche)} niche types also missing: {', '.join(t.split(chr(39))[1] for t in missing_niche)})")

    return gaps


def check_filter_modes(examples: dict[str, str]) -> list[str]:
    """Check that all filter type modes are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    for mode in sorted(get_filter_modes()):
        if not re.search(rf'type:\s*{re.escape(mode)}\b', all_content, re.IGNORECASE):
            gaps.append(f"Filter mode '{mode}' — not demonstrated in any example")

    return gaps


def check_cf_modes(examples: dict[str, str]) -> list[str]:
    """Check that all conditional formatting modes are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    for mode in sorted(get_cf_modes()):
        if not re.search(rf'mode:\s*{re.escape(mode)}\b', all_content, re.IGNORECASE):
            gaps.append(f"CF mode '{mode}' — not demonstrated in any example")

    return gaps


def check_interaction_types(examples: dict[str, str]) -> list[str]:
    """Check that all interaction types are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    for itype in sorted(get_interaction_types()):
        if not re.search(rf'type:\s*{re.escape(itype)}\b', all_content):
            gaps.append(f"Interaction type '{itype}' — not demonstrated in any example")

    return gaps


def check_page_yaml_features(examples: dict[str, str]) -> list[str]:
    """Check that all special page-level YAML keys are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    # Keys that are structural/internal and don't need examples
    skip = {"name", "width", "height", "visuals", "bookmarks", "type", "pageBinding"}

    for key in sorted(get_page_yaml_keys() - skip):
        if not re.search(rf'^\s*{re.escape(key)}\s*:', all_content, re.MULTILINE):
            gaps.append(f"Page-level key '{key}' — not demonstrated in any example")

    return gaps


def check_visual_yaml_features(examples: dict[str, str]) -> list[str]:
    """Check that all special visual-level YAML keys are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    # Keys that are structural/internal and don't need examples
    skip = {"id", "name", "type", "pbir", "layout", "accentBar", "referenceLabelLayout"}

    for key in sorted(get_visual_yaml_keys() - skip):
        if not re.search(rf'^\s*{re.escape(key)}\s*:', all_content, re.MULTILINE):
            gaps.append(f"Visual-level key '{key}' — not demonstrated in any example")

    return gaps


def check_bookmark_fields(examples: dict[str, str]) -> list[str]:
    """Check that bookmark fields are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    # Only check non-obvious fields
    skip = {"name", "page"}

    for field in sorted(get_bookmark_fields() - skip):
        if not re.search(rf'^\s*{re.escape(field)}\s*:', all_content, re.MULTILINE):
            gaps.append(f"Bookmark field '{field}' — not demonstrated in any example")

    return gaps


def check_binding_formats(examples: dict[str, str]) -> list[str]:
    """Check that all binding syntaxes are demonstrated."""
    gaps = []
    all_content = "\n".join(examples.values())

    checks = [
        ("Simple string binding", r'bindings:\s*\n\s+\w+:\s+\w+\.\w+'),
        ("Measure binding (suffix)", r'\(measure\)'),
        ("Object binding (field: key)", r'field:\s+\w+\.\w+'),
        ("Display name", r'displayName:'),
        ("Column width", r'width:\s+\d+'),
        ("Sort definition", r'sort:'),
    ]

    for label, pattern in checks:
        if not re.search(pattern, all_content, re.MULTILINE):
            gaps.append(f"Binding format '{label}' — not demonstrated in any example")

    return gaps


def check_complete_example_exists(examples: dict[str, str]) -> list[str]:
    """Check that complete-page.yaml exists and has minimum content."""
    gaps = []
    content = examples.get("complete-page.yaml", "")

    if not content:
        gaps.append("complete-page.yaml is missing")
        return gaps

    required = [
        ("pages:", "top-level pages key"),
        ("visuals:", "visuals section"),
        ("bindings:", "at least one binding"),
        ("filters:", "at least one filter"),
        ("position:", "visual positioning"),
        ("size:", "visual sizing"),
        ("title:", "visual title"),
        ("border:", "border formatting"),
    ]

    for pattern, label in required:
        if pattern not in content:
            gaps.append(f"complete-page.yaml is missing {label} ({pattern})")

    return gaps


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    examples = read_all_examples()

    if not examples:
        print(f"ERROR: No .yaml files found in {EXAMPLES_DIR}")
        return 1

    print(f"Scanning {len(examples)} example file(s) in {EXAMPLES_DIR.relative_to(PROJECT_ROOT)}/\n")

    all_gaps: list[tuple[str, list[str]]] = []

    checks = [
        ("Visual types", check_visual_types),
        ("Filter modes", check_filter_modes),
        ("CF modes", check_cf_modes),
        ("Interaction types", check_interaction_types),
        ("Page YAML features", check_page_yaml_features),
        ("Visual YAML features", check_visual_yaml_features),
        ("Bookmark fields", check_bookmark_fields),
        ("Binding formats", check_binding_formats),
        ("Complete example", check_complete_example_exists),
    ]

    for label, check_fn in checks:
        gaps = check_fn(examples)
        all_gaps.append((label, gaps))

    # Report
    total_gaps = 0
    for label, gaps in all_gaps:
        if gaps:
            print(f"  {label}:")
            for gap in gaps:
                print(f"    - {gap}")
            total_gaps += len(gaps)
        else:
            print(f"  {label}: OK")

    print()
    if total_gaps == 0:
        print("All checks passed. YAML examples cover all current features.")
        return 0
    else:
        print(f"{total_gaps} gap(s) found. Consider adding examples for the missing features.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
