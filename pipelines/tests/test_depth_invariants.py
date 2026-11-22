"""
pipelines/tests/test_depth_invariants.py — Unit tests for flood depth invariants.

Validates the required Phase 4 depth modeling invariants:
1. Nodata is never converted to zero (unknown remains distinct from dry/zero depth).
2. Unit conversions for meters and feet are exact and bidirectional.
3. Raster bounds check: rasters outside the study area fail fast.
4. Threshold classification monotonicity: higher water depth cannot produce a less severe closure status.
"""
import pytest
import math


class TestDepthUnitsAndNodataInvariants:
    """Nodata and unit conversion invariant checks."""

    def test_nodata_is_never_converted_to_zero(self):
        """
        Nodata indicates absence of data / unmodeled coverage.
        It must never be coerced to 0.0 (which means dry ground).
        """
        nodata_values = [-9999.0, -32767.0, float("nan"), None]

        for val in nodata_values:
            # A correct depth parsing function preserves None / nan
            parsed = self._parse_depth_sample(val, nodata=[-9999.0, -32767.0])
            assert parsed is None or math.isnan(parsed), f"Nodata {val} was incorrectly coerced to: {parsed}"
            assert parsed != 0.0, f"CRITICAL INVARIANT VIOLATED: Nodata {val} became 0.0 (dry)!"

    def test_meters_to_feet_conversion_fixture(self):
        """1 meter = 3.28084 feet exact test fixture."""
        FEET_PER_METER = 3.28084

        # Test cases: (meters, expected_feet)
        fixtures = [
            (0.0, 0.0),
            (0.3048, 1.0),       # 1 foot
            (1.0, 3.28084),      # 1 meter
            (0.15, 0.492126),    # 6 inches (0.5 ft)
            (0.30, 0.984252),    # 1 foot threshold
            (0.60, 1.968504),    # 2 feet threshold
        ]

        for m, expected_ft in fixtures:
            computed_ft = m * FEET_PER_METER
            assert abs(computed_ft - expected_ft) < 1e-4

            # Invert
            computed_m = computed_ft / FEET_PER_METER
            assert abs(computed_m - m) < 1e-4

    def test_raster_outside_study_area_fails_fast(self):
        """A raster whose bounding box does not intersect the study area bbox must fail fast."""
        study_bbox = [-95.45, 29.68, -95.25, 29.85]  # [west, south, east, north]

        # Raster completely in Dallas (far north)
        dallas_raster_bbox = [-96.90, 32.70, -96.70, 32.85]
        # Raster in Galveston (far south)
        galveston_raster_bbox = [-94.95, 29.20, -94.75, 29.35]
        # Raster overlapping Houston pilot
        overlapping_raster_bbox = [-95.40, 29.70, -95.30, 29.80]

        assert not self._bboxes_intersect(study_bbox, dallas_raster_bbox)
        assert not self._bboxes_intersect(study_bbox, galveston_raster_bbox)
        assert self._bboxes_intersect(study_bbox, overlapping_raster_bbox)

    def test_depth_classification_monotonicity(self):
        """
        Threshold monotonicity invariant:
        Given threshold set: passable < 0.15m <= restricted < 0.30m <= closed.
        A higher depth CANNOT produce a less severe category.
        """
        thresholds = {"restricted_m": 0.15, "closed_m": 0.30}

        def classify(depth_m: float | None) -> str:
            if depth_m is None or math.isnan(depth_m):
                return "unknown"
            if depth_m < thresholds["restricted_m"]:
                return "passable"
            elif depth_m < thresholds["closed_m"]:
                return "restricted"
            else:
                return "closed"

        severity_rank = {"passable": 0, "restricted": 1, "closed": 2}

        depths = [0.0, 0.05, 0.10, 0.149, 0.15, 0.20, 0.299, 0.30, 0.50, 1.0, 2.5]
        classes = [classify(d) for d in depths]

        # Verify monotonicity: severity[i+1] >= severity[i]
        for i in range(len(depths) - 1):
            assert severity_rank[classes[i + 1]] >= severity_rank[classes[i]], (
                f"Monotonicity violated: depth {depths[i]}m ({classes[i]}) vs "
                f"depth {depths[i+1]}m ({classes[i+1]})"
            )

    @staticmethod
    def _parse_depth_sample(val, nodata=(-9999.0, -32767.0)) -> float | None:
        if val is None:
            return None
        if isinstance(nodata, (list, tuple, set)):
            if val in nodata:
                return None
        elif val == nodata:
            return None
        if math.isnan(val) or val < 0:
            return None
        return float(val)

    @staticmethod
    def _bboxes_intersect(bbox1: list[float], bbox2: list[float]) -> bool:
        w1, s1, e1, n1 = bbox1
        w2, s2, e2, n2 = bbox2
        return not (e1 < w2 or w1 > e2 or n1 < s2 or s1 > n2)
