"""Textbox content helpers shared by CLI, export, and apply paths."""

from __future__ import annotations

from typing import Any

from pbi.properties import decode_pbi_value


def extract_textbox_spec(visual_data: dict) -> dict[str, Any] | None:
    """Extract textbox body content into export/apply shorthand."""
    run = _first_text_run(visual_data)
    if not isinstance(run, dict):
        return None

    text = _decode_text_literal(run.get("value", ""))
    if text == "":
        return None

    result: dict[str, Any] = {"text": text}
    text_style = _decode_text_style(run.get("textStyle", {}))
    if text_style:
        result["textStyle"] = text_style
    return result


def set_textbox_content(
    visual_data: dict,
    *,
    text: str | None = None,
    style_updates: dict[str, Any] | None = None,
) -> None:
    """Set textbox content while preserving the canonical paragraphs/textRuns shape."""
    visual = visual_data.setdefault("visual", {})
    objects = visual.setdefault("objects", {})
    general_entries = objects.setdefault("general", [{}])
    if not isinstance(general_entries, list) or not general_entries:
        general_entries = [{}]
        objects["general"] = general_entries

    if not isinstance(general_entries[0], dict):
        general_entries[0] = {}

    properties = general_entries[0].setdefault("properties", {})
    if not isinstance(properties, dict):
        properties = {}
        general_entries[0]["properties"] = properties

    run = _first_text_run(visual_data)
    if not isinstance(run, dict):
        run = {}

    if text is not None:
        run["value"] = str(text)
    elif _is_quoted(run.get("value")):
        run["value"] = _decode_text_literal(run["value"])

    style = run.get("textStyle")
    if isinstance(style, dict):
        _repair_legacy_style(style)
    if style_updates:
        if not isinstance(style, dict):
            style = {}
        _apply_style_updates(style, style_updates)
        if style:
            run["textStyle"] = style
        else:
            run.pop("textStyle", None)

    properties["paragraphs"] = [{"textRuns": [run]}]

    # Repair the incorrect imperative-path shape if it was created earlier.
    objects.pop("paragraph", None)


def textbox_content_matches(
    visual_data: dict,
    *,
    text: str,
    style_updates: dict[str, Any] | None = None,
) -> bool:
    """True when the textbox already shows ``text`` with every style in ``style_updates``.

    Compares what ``extract_textbox_spec`` reads back, so an unedited
    export -> apply leaves the visual's paragraphs and runs as they are.
    """
    spec = extract_textbox_spec(visual_data) or {}
    if spec.get("text", "") != str(text):
        return False
    current = spec.get("textStyle", {})
    for key, value in (style_updates or {}).items():
        if key == "fontSize":
            if normalize_font_size(value) != current.get("fontSize"):
                return False
        elif key in {"bold", "italic"}:
            if bool(value) != bool(current.get(key, False)):
                return False
        elif key == "fontColor":
            if str(value).strip().lower() != str(current.get("fontColor", "")).lower():
                return False
        elif key == "fontFamily":
            if str(value).strip() != current.get("fontFamily", ""):
                return False
        else:
            return False
    return True


def textbox_text(visual_data: dict) -> str | None:
    """Return textbox body text if present."""
    spec = extract_textbox_spec(visual_data)
    if spec is None:
        return None
    return spec.get("text")


def textbox_text_style_value(visual_data: dict, key: str) -> Any:
    """Return one textbox style field from the shorthand representation."""
    spec = extract_textbox_spec(visual_data)
    if spec is None:
        return None
    style = spec.get("textStyle", {})
    if not isinstance(style, dict):
        return None
    return style.get(key)


def parse_textbox_style_value(key: str, value: str) -> Any:
    """Parse CLI textbox style assignments."""
    if key == "fontSize":
        return normalize_font_size(value)
    if key in {"bold", "italic"}:
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"{key} must be true or false.")
    return value


def normalize_font_size(value: Any) -> int | float:
    """Parse a font size in points from ``22``, ``22.5`` or ``"22pt"``."""
    if isinstance(value, bool):
        raise ValueError(f"fontSize must be a number of points, got {value!r}.")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().strip("'").strip()
        if text.lower().endswith("pt"):
            text = text[:-2].strip()
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"fontSize must be a number of points such as 22 or 22pt, got {value!r}.") from None
    if number <= 0:
        raise ValueError(f"fontSize must be positive, got {value!r}.")
    return int(number) if number.is_integer() else number


def is_legacy_quoted_run(run: Any) -> bool:
    """True when a text run carries the old CLI encoding (quoted literals, colour expr)."""
    if not isinstance(run, dict):
        return False
    if _is_quoted(run.get("value")):
        return True
    style = run.get("textStyle")
    if not isinstance(style, dict):
        return False
    if isinstance(style.get("color"), dict):
        return True
    return any(_is_quoted(style.get(key)) for key in _STYLE_STRING_KEYS)


def _first_text_run(visual_data: dict) -> dict[str, Any] | None:
    paragraphs = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get("general", [{}])[0]
        .get("properties", {})
        .get("paragraphs", [])
    )
    if not isinstance(paragraphs, list) or not paragraphs:
        return None
    first_para = paragraphs[0]
    if not isinstance(first_para, dict):
        return None
    text_runs = first_para.get("textRuns", [])
    if not isinstance(text_runs, list) or not text_runs:
        return None
    run = text_runs[0]
    return run if isinstance(run, dict) else None


_STYLE_STRING_KEYS = ("fontFamily", "fontSize", "fontWeight", "fontStyle", "color")


def _is_quoted(value: Any) -> bool:
    return isinstance(value, str) and len(value) >= 2 and value.startswith("'") and value.endswith("'")


def _decode_text_literal(raw_text: Any) -> str:
    if _is_quoted(raw_text):
        return raw_text[1:-1].replace("''", "'")
    return str(raw_text)


def _decode_text_style(raw_style: Any) -> dict[str, Any]:
    if not isinstance(raw_style, dict):
        return {}

    text_style: dict[str, Any] = {}
    font_family = raw_style.get("fontFamily")
    if isinstance(font_family, str) and _decode_text_literal(font_family):
        text_style["fontFamily"] = _decode_text_literal(font_family)

    font_size = raw_style.get("fontSize")
    if isinstance(font_size, (str, int, float)) and font_size != "":
        try:
            text_style["fontSize"] = normalize_font_size(font_size)
        except ValueError:
            pass

    color = raw_style.get("color")
    if isinstance(color, dict):
        decoded = decode_pbi_value(color)
        if decoded:
            text_style["fontColor"] = decoded
    elif isinstance(color, str) and color:
        text_style["fontColor"] = _decode_text_literal(color)

    font_weight = raw_style.get("fontWeight")
    if isinstance(font_weight, str) and "bold" in font_weight.lower():
        text_style["bold"] = True

    font_style = raw_style.get("fontStyle")
    if isinstance(font_style, str) and "italic" in font_style.lower():
        text_style["italic"] = True

    return text_style


def _repair_legacy_style(style: dict[str, Any]) -> None:
    """Rewrite old quoted textStyle values in place as Desktop's plain strings."""
    for key in _STYLE_STRING_KEYS:
        value = style.get(key)
        if key == "color" and isinstance(value, dict):
            decoded = decode_pbi_value(value)
            if isinstance(decoded, str) and decoded:
                style[key] = decoded.lower() if decoded.startswith("#") else decoded
            continue
        if _is_quoted(value):
            style[key] = _decode_text_literal(value)


def _apply_style_updates(style: dict[str, Any], updates: dict[str, Any]) -> None:
    """Write textStyle values as Desktop does: plain strings, ``"24pt"``, lowercase hex."""
    if "fontFamily" in updates:
        family = str(updates["fontFamily"]).strip()
        if family:
            style["fontFamily"] = family
        else:
            style.pop("fontFamily", None)
    if "fontSize" in updates:
        style["fontSize"] = f"{normalize_font_size(updates['fontSize'])}pt"
    if "fontColor" in updates:
        color = str(updates["fontColor"]).strip()
        style["color"] = color.lower() if color.startswith("#") else color
    if "bold" in updates:
        if updates["bold"]:
            style["fontWeight"] = "bold"
        else:
            style.pop("fontWeight", None)
    if "italic" in updates:
        if updates["italic"]:
            style["fontStyle"] = "italic"
        else:
            style.pop("fontStyle", None)
