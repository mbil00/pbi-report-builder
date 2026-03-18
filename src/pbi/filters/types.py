from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FilterInfo:
    """Parsed filter for display."""

    name: str
    field_entity: str
    field_prop: str
    filter_type: str
    values: list[str]
    is_hidden: bool
    is_locked: bool
    level: str  # "report", "page", or "visual"


@dataclass(frozen=True)
class TupleField:
    """One field/value pair within a tuple filter row."""

    entity: str
    prop: str
    value: str
    field_type: str = "column"
    data_type: str | None = None


DATE_UNIT_CODES = {
    "Days": 0,
    "Weeks": 1,
    "CalendarWeeks": 2,
    "Months": 3,
    "CalendarMonths": 4,
    "Years": 5,
    "CalendarYears": 6,
}

TIME_UNIT_CODES = {
    "Minutes": 7,
    "Hours": 8,
}

ADVANCED_OPERATORS: dict[str, tuple[str, int | None, bool, bool]] = {
    "is": ("Comparison", 0, False, True),
    "is-not": ("Comparison", 0, True, True),
    "less-than": ("Comparison", 3, False, True),
    "less-than-or-equal": ("Comparison", 4, False, True),
    "greater-than": ("Comparison", 1, False, True),
    "greater-than-or-equal": ("Comparison", 2, False, True),
    "contains": ("Contains", None, False, True),
    "does-not-contain": ("Contains", None, True, True),
    "starts-with": ("StartsWith", None, False, True),
    "does-not-start-with": ("StartsWith", None, True, True),
    "is-blank": ("Comparison", 0, False, False),
    "is-not-blank": ("Comparison", 0, True, False),
    "is-empty": ("Comparison", 0, False, False),
    "is-not-empty": ("Comparison", 0, True, False),
}
