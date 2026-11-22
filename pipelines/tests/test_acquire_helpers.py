from __future__ import annotations

import sys
import unittest
from pathlib import Path


ACQUIRE_ROOT = Path(__file__).resolve().parents[1] / "acquire"
sys.path.insert(0, str(ACQUIRE_ROOT))

from common import bbox_text, parse_bbox  # noqa: E402
from download_census_population import normalize_acs  # noqa: E402


class AcquireHelperTests(unittest.TestCase):
    def test_bbox_parsing(self) -> None:
        bbox = parse_bbox("-95.45,29.68,-95.25,29.85")
        self.assertEqual(bbox, (-95.45, 29.68, -95.25, 29.85))
        self.assertEqual(bbox_text(bbox), "-95.45,29.68,-95.25,29.85")

    def test_bbox_rejects_reversed_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            parse_bbox("-95.2,29.9,-95.5,29.6")

    def test_census_rows_receive_twelve_character_geoid(self) -> None:
        payload = [
            ["NAME", "B01003_001E", "state", "county", "tract", "block group"],
            ["Example", "1250", "48", "201", "012300", "2"],
        ]
        row = normalize_acs(payload)[0]
        self.assertEqual(row["GEOID"], "482010123002")
        self.assertEqual(row["population"], 1250)


if __name__ == "__main__":
    unittest.main()
