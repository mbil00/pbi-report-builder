"""Desktop-derived semantic-model metadata enums and normalizers.

These values are taken from the extracted Power BI Desktop bundle in
`schema-analysis/output/DESKTOP.MIN.JS`, which exposes canonical enums for
data types, summarize-by behavior, relationship directions, and data
categories.
"""

from __future__ import annotations


_DESKTOP_DATA_TYPE_MAP = {
    "binary": "binary",
    "boolean": "boolean",
    "bool": "boolean",
    "currency": "decimal",
    "date": "date",
    "datetime": "dateTime",
    "date/time": "dateTime",
    "decimal": "decimal",
    "double": "double",
    "int": "int64",
    "integer": "int64",
    "number": "double",
    "string": "string",
    "text": "string",
    "time": "time",
    "variant": "variant",
    "whole": "int64",
    "wholenumber": "int64",
    "whole number": "int64",
    "int64": "int64",
}

_CANONICAL_MODEL_DATA_TYPES = frozenset({
    "binary",
    "boolean",
    "date",
    "dateTime",
    "decimal",
    "double",
    "int64",
    "string",
    "time",
    "variant",
})

_DESKTOP_SUMMARIZE_BY_MAP = {
    "average": "average",
    "count": "count",
    "default": "default",
    "distinctcount": "distinctCount",
    "distinct count": "distinctCount",
    "max": "max",
    "min": "min",
    "none": "none",
    "sum": "sum",
}

_CANONICAL_SUMMARIZE_BY_VALUES = frozenset({
    "average",
    "count",
    "default",
    "distinctCount",
    "max",
    "min",
    "none",
    "sum",
})

_CANONICAL_DATA_CATEGORIES = (
    "Address",
    "Barcode",
    "City",
    "Continent",
    "Country",
    "County",
    "Date",
    "DateKey",
    "PaddedDateTableDates",
    "DayOfMonth",
    "DayOfWeek",
    "DayOfWeekNumber",
    "ImageUrl",
    "Latitude",
    "Longitude",
    "Month",
    "Months",
    "MonthNumber",
    "MonthOfYear",
    "MonthYear",
    "Place",
    "PostalCode",
    "Quarter",
    "Quarters",
    "QuarterNumber",
    "QuarterOfYear",
    "QuarterYear",
    "StateOrProvince",
    "Time",
    "Uncategorized",
    "WebUrl",
    "Week",
    "WeekNumber",
    "WeekYear",
    "Year",
    "Years",
    "YearMonthNumber",
    "YearNumber",
    "YearQuarterNumber",
)
_DATA_CATEGORY_LOOKUP = {value.lower(): value for value in _CANONICAL_DATA_CATEGORIES}


def allowed_model_data_types() -> tuple[str, ...]:
    return tuple(sorted(_CANONICAL_MODEL_DATA_TYPES))


def allowed_summarize_by_values() -> tuple[str, ...]:
    return tuple(sorted(_CANONICAL_SUMMARIZE_BY_VALUES))


def allowed_data_categories() -> tuple[str, ...]:
    return tuple(_CANONICAL_DATA_CATEGORIES)


def normalize_model_data_type(value: str) -> str:
    text = str(value).strip()
    normalized = _DESKTOP_DATA_TYPE_MAP.get(text.lower())
    if normalized is None:
        allowed = ", ".join(allowed_model_data_types())
        raise ValueError(f'Invalid dataType "{value}". Allowed: {allowed}')
    return normalized


def normalize_summarize_by(value: str) -> str:
    text = str(value).strip()
    normalized = _DESKTOP_SUMMARIZE_BY_MAP.get(text.lower())
    if normalized is None:
        allowed = ", ".join(allowed_summarize_by_values())
        raise ValueError(f'Invalid summarizeBy "{value}". Allowed: {allowed}')
    return normalized


def normalize_data_category(value: str) -> str:
    text = str(value).strip()
    normalized = _DATA_CATEGORY_LOOKUP.get(text.lower())
    if normalized is None:
        allowed = ", ".join(allowed_data_categories())
        raise ValueError(f'Invalid dataCategory "{value}". Allowed: {allowed}')
    return normalized


def normalize_table_data_category(value: str) -> str:
    normalized = normalize_data_category(value)
    if normalized != "Time":
        raise ValueError('Invalid table dataCategory "{0}". Allowed: Time'.format(value))
    return normalized
