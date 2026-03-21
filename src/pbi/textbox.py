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
        run["value"] = _encode_text_literal(text)

    if style_updates:
        style = run.get("textStyle", {})
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
        return int(value)
    if key in {"bold", "italic"}:
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"{key} must be true or false.")
    return value


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


def _encode_text_literal(text: str) -> str:
    escaped = str(text).replace("'", "''")
    return f"'{escaped}'"


def _decode_text_literal(raw_text: str) -> str:
    if isinstance(raw_text, str) and raw_text.startswith("'") and raw_text.endswith("'"):
        return raw_text[1:-1].replace("''", "'")
    return str(raw_text)


def _decode_text_style(raw_style: Any) -> dict[str, Any]:
    if not isinstance(raw_style, dict):
        return {}

    text_style: dict[str, Any] = {}
    font_family = raw_style.get("fontFamily", "")
    if isinstance(font_family, str) and font_family.strip("'"):
        text_style["fontFamily"] = font_family.strip("'")

    font_size = raw_style.get("fontSize", "")
    if isinstance(font_size, str):
        stripped = font_size.strip("'").rstrip("pt")
        if stripped:
            text_style["fontSize"] = int(stripped)

    color = raw_style.get("color")
    if isinstance(color, dict):
        decoded = decode_pbi_value(color)
        if decoded:
            text_style["fontColor"] = decoded
    elif isinstance(color, str):
        text_style["fontColor"] = color.strip("'")

    font_weight = raw_style.get("fontWeight", "")
    if isinstance(font_weight, str) and "bold" in font_weight.lower():
        text_style["bold"] = True

    font_style = raw_style.get("fontStyle", "")
    if isinstance(font_style, str) and "italic" in font_style.lower():
        text_style["italic"] = True

    return text_style


def _apply_style_updates(style: dict[str, Any], updates: dict[str, Any]) -> None:
    if "fontFamily" in updates:
        style["fontFamily"] = _encode_text_literal(str(updates["fontFamily"]))
    if "fontSize" in updates:
        style["fontSize"] = _encode_text_literal(f"{int(updates['fontSize'])}pt")
    if "fontColor" in updates:
        style["color"] = {"expr": {"Literal": {"Value": _encode_text_literal(str(updates["fontColor"]))}}}
    if "bold" in updates:
        style["fontWeight"] = _encode_text_literal("bold" if updates["bold"] else "normal")
    if "italic" in updates:
        style["fontStyle"] = _encode_text_literal("italic" if updates["italic"] else "normal")
