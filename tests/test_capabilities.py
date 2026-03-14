from __future__ import annotations

import json
import unittest

from pbi.capabilities import list_capabilities


class CapabilityMatrixTests(unittest.TestCase):
    def test_matrix_contains_core_blocked_filter_gap(self) -> None:
        blocked = list_capabilities("blocked")
        features = {cap.feature for cap in blocked}
        self.assertIn(
            "Passthrough filters",
            features,
        )

    def test_matrix_can_be_serialized(self) -> None:
        payload = [cap.to_dict() for cap in list_capabilities()]
        text = json.dumps(payload)
        self.assertIn("supported", text)
        self.assertIn("partial", text)
        self.assertIn("blocked", text)


if __name__ == "__main__":
    unittest.main()
