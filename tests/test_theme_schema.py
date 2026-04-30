"""Tests for the Theme Schema seam.

The seam is ``theme_schema.validate_and_encode`` (the only validated path for
writes into theme document properties) plus the tightened
``theme_migration._migrate_visual_colors`` which now consults the Visual
Schema before rewriting a colour into a non-colour target.
"""

from __future__ import annotations

import unittest

from pbi.theme_migration import SkippedColorWrite, _migrate_visual_colors
from pbi.theme_schema import (
    THEME_PROPERTIES,
    ThemeProperty,
    list_properties,
    lookup_property,
    validate_and_encode,
)


class TestValidateAndEncode(unittest.TestCase):
    def test_color_returns_uppercase_hex(self) -> None:
        self.assertEqual(validate_and_encode("foreground", "#aabbcc"), "#AABBCC")

    def test_color_short_form_expanded(self) -> None:
        self.assertEqual(validate_and_encode("foreground", "#abc"), "#AABBCC")

    def test_color_with_alpha(self) -> None:
        self.assertEqual(validate_and_encode("foreground", "#aabbccdd"), "#AABBCCDD")

    def test_color_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_encode("foreground", "red")
        with self.assertRaises(ValueError):
            validate_and_encode("foreground", "#GG0000")

    def test_color_list_splits_and_validates_each(self) -> None:
        result = validate_and_encode("dataColors", "#FF0000, #00FF00, #0000FF")
        self.assertEqual(result, ["#FF0000", "#00FF00", "#0000FF"])

    def test_color_list_short_form_expanded(self) -> None:
        self.assertEqual(
            validate_and_encode("dataColors", "#abc,#def"),
            ["#AABBCC", "#DDEEFF"],
        )

    def test_color_list_rejects_invalid_member(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_encode("dataColors", "#FF0000,not-a-color")

    def test_color_list_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_encode("dataColors", "")

    def test_number_int(self) -> None:
        self.assertEqual(validate_and_encode("textClasses.title.fontSize", "14"), 14)

    def test_number_float(self) -> None:
        self.assertEqual(validate_and_encode("textClasses.title.fontSize", "14.5"), 14.5)

    def test_number_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_encode("textClasses.title.fontSize", "big")

    def test_string_passes_through(self) -> None:
        self.assertEqual(
            validate_and_encode("textClasses.title.fontFace", "Segoe UI"),
            "Segoe UI",
        )

    def test_unknown_property_raises_with_suggestion(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_and_encode("foregrond", "#FF0000")
        self.assertIn("foreground", str(ctx.exception))

    def test_unknown_property_no_close_match(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_and_encode("totallyMadeUpThing", "#FF0000")
        self.assertIn("totallyMadeUpThing", str(ctx.exception))


class TestSchemaCoverage(unittest.TestCase):
    """Property-driven: every catalog entry encodes a representative input."""

    def test_every_entry_accepts_a_representative_value(self) -> None:
        sample_by_type = {
            "color": "#112233",
            "color[]": "#FF0000,#00FF00",
            "number": "12",
            "string": "Segoe UI",
        }
        for prop in list_properties():
            sample = sample_by_type.get(prop.prop_type)
            if sample is None:
                self.fail(
                    f"theme_schema has property {prop.path!r} of unhandled type "
                    f"{prop.prop_type!r} — extend this test or _encode in theme_schema",
                )
            validate_and_encode(prop.path, sample)

    def test_back_compat_tuple_view_matches_dataclass(self) -> None:
        for tup, prop in zip(THEME_PROPERTIES, list_properties(), strict=True):
            self.assertEqual(tup, (prop.path, prop.prop_type, prop.description))


class TestLookup(unittest.TestCase):
    def test_lookup_known(self) -> None:
        prop = lookup_property("foreground")
        self.assertIsInstance(prop, ThemeProperty)
        assert prop is not None
        self.assertEqual(prop.prop_type, "color")

    def test_lookup_unknown_returns_none(self) -> None:
        self.assertIsNone(lookup_property("notARealProperty"))


class TestMigrationVisualSchemaSkip(unittest.TestCase):
    """Migration must skip writes when the target schema disagrees with 'color'.

    These tests exercise the seam directly with hand-built visual data, so they
    don't depend on a full PBIP fixture.
    """

    def _color_value(self, hex_color: str) -> dict:
        return {"solid": {"color": hex_color}}

    def test_color_target_is_rewritten(self) -> None:
        data = {
            "visual": {
                "visualType": "barChart",
                "objects": {
                    "background": [
                        {"properties": {"color": self._color_value("#FF0000")}},
                    ],
                },
            },
        }
        skipped: list[SkippedColorWrite] = []
        changed = _migrate_visual_colors(
            data, {"#FF0000": "#00FF00"}, dry_run=False, skipped=skipped,
        )
        self.assertTrue(changed)
        self.assertEqual(skipped, [])

    def test_non_color_target_is_skipped(self) -> None:
        # 'fontSize' on a barChart's labels is a number, not a color — even
        # though we accidentally found a colour-shaped value at that key,
        # rewriting would produce malformed PBIR. The seam rejects it.
        data = {
            "visual": {
                "visualType": "barChart",
                "objects": {
                    "labels": [
                        {"properties": {"fontSize": self._color_value("#FF0000")}},
                    ],
                },
            },
        }
        skipped: list[SkippedColorWrite] = []
        original = data["visual"]["objects"]["labels"][0]["properties"]["fontSize"]
        changed = _migrate_visual_colors(
            data, {"#FF0000": "#00FF00"}, dry_run=False, skipped=skipped,
        )
        self.assertFalse(changed)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].visual_type, "barChart")
        self.assertEqual(skipped[0].object_name, "labels")
        self.assertEqual(skipped[0].property_name, "fontSize")
        self.assertEqual(
            data["visual"]["objects"]["labels"][0]["properties"]["fontSize"],
            original,
        )

    def test_unknown_schema_falls_through(self) -> None:
        # When the schema can't tell us the target's type (unknown visual type
        # or unknown property), preserve the old behaviour — write anyway —
        # rather than over-skip and lose migration coverage.
        data = {
            "visual": {
                "visualType": "completelyMadeUpVisualType",
                "objects": {
                    "background": [
                        {"properties": {"color": self._color_value("#FF0000")}},
                    ],
                },
            },
        }
        skipped: list[SkippedColorWrite] = []
        changed = _migrate_visual_colors(
            data, {"#FF0000": "#00FF00"}, dry_run=False, skipped=skipped,
        )
        self.assertTrue(changed)
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()
