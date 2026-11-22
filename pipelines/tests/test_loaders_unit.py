"""
tests/test_loaders_unit.py — Unit tests for loader helper functions.
These tests require no database connection.
"""
import json
import pytest
import sys
from pathlib import Path

# Add pipelines/load to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines" / "load"))
sys.path.insert(0, str(ROOT / "pipelines"))


class TestNetworkSpeedResolution:
    def setup_method(self):
        from load_osm_network import _resolve_speed, _travel_time_s
        self._resolve_speed = _resolve_speed
        self._travel_time_s = _travel_time_s

    def test_tagged_speed(self):
        speed, src = self._resolve_speed({"speed_kph": 48.0})
        assert speed == 48.0
        assert src == "tagged"

    def test_highway_default_residential(self):
        speed, src = self._resolve_speed({"highway": "residential"})
        assert speed == 32.0
        assert src == "highway_default"

    def test_highway_default_motorway(self):
        speed, src = self._resolve_speed({"highway": "motorway"})
        assert speed == 97.0
        assert src == "highway_default"

    def test_fallback_unknown_highway(self):
        speed, src = self._resolve_speed({"highway": "unknown_type"})
        assert speed == 32.0
        assert src == "fallback"

    def test_fallback_no_highway(self):
        speed, src = self._resolve_speed({})
        assert speed == 32.0
        assert src == "fallback"

    def test_travel_time_calculation(self):
        # 100m at 36 km/h = 10 seconds exactly
        t = self._travel_time_s(100.0, 36.0)
        assert abs(t - 10.0) < 0.001

    def test_travel_time_zero_speed_raises(self):
        with pytest.raises(ValueError):
            self._travel_time_s(100.0, 0.0)

    def test_travel_time_residential(self):
        # 500m at 32 km/h → 500/(32/3.6) = 56.25 seconds
        t = self._travel_time_s(500.0, 32.0)
        assert abs(t - 56.25) < 0.1

    def test_list_highway_uses_first(self):
        """OSMnx sometimes returns highway as a list."""
        speed, src = self._resolve_speed({"highway": ["primary", "secondary"]})
        assert speed == 72.0
        assert src == "highway_default"


class TestFEMAGeometryConversion:
    def setup_method(self):
        from load_fema_hazard import _geojson_to_wkt
        self._geojson_to_wkt = _geojson_to_wkt

    def test_polygon_wkt(self):
        coords = [[[-95.4, 29.7], [-95.3, 29.7], [-95.3, 29.8], [-95.4, 29.8], [-95.4, 29.7]]]
        wkt = self._geojson_to_wkt("Polygon", coords)
        assert wkt.startswith("POLYGON")
        assert "-95.4 29.7" in wkt

    def test_multipolygon_wkt(self):
        coords = [
            [[[-95.4, 29.7], [-95.3, 29.7], [-95.3, 29.8], [-95.4, 29.8], [-95.4, 29.7]]]
        ]
        wkt = self._geojson_to_wkt("MultiPolygon", coords)
        assert wkt.startswith("MULTIPOLYGON")

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError):
            self._geojson_to_wkt("Point", [[0, 0]])


class TestCensusSpecialValues:
    """Census special negative values must never become population."""

    def test_special_values_excluded(self):
        from load_census_origins import CENSUS_SPECIAL_VALUES
        assert -666666666 in CENSUS_SPECIAL_VALUES
        assert -999999999 in CENSUS_SPECIAL_VALUES
        # All special values are negative
        assert all(v < 0 for v in CENSUS_SPECIAL_VALUES)

    def test_zero_population_allowed(self):
        """Zero is a valid Census population (unpopulated BG)."""
        from load_census_origins import CENSUS_SPECIAL_VALUES
        assert 0 not in CENSUS_SPECIAL_VALUES


class TestStudyAreaWKT:
    def setup_method(self):
        from load_study_area import _ring_wkt, _coords_to_wkt
        self._ring_wkt = _ring_wkt
        self._coords_to_wkt = _coords_to_wkt

    def test_ring_wkt(self):
        ring = [[-95.4, 29.7], [-95.3, 29.7], [-95.3, 29.8], [-95.4, 29.7]]
        wkt = self._ring_wkt(ring)
        assert wkt.startswith("(")
        assert wkt.endswith(")")
        assert "-95.4 29.7" in wkt

    def test_polygon_coords(self):
        coords = [[[-95.4, 29.7], [-95.3, 29.7], [-95.3, 29.8], [-95.4, 29.7]]]
        result = self._coords_to_wkt(coords, "Polygon")
        assert "((" in result

    def test_multipolygon_coords(self):
        coords = [[[[-95.4, 29.7], [-95.3, 29.7], [-95.3, 29.8], [-95.4, 29.7]]]]
        result = self._coords_to_wkt(coords, "MultiPolygon")
        assert "(((" in result


class TestFacilityMapping:
    def test_known_amenities_mapped(self):
        from load_facilities import AMENITY_TO_TYPE
        assert AMENITY_TO_TYPE["hospital"] == "hospital"
        assert AMENITY_TO_TYPE["fire_station"] == "fire_station"
        assert AMENITY_TO_TYPE["clinic"] == "hospital"

    def test_all_values_valid_facility_types(self):
        from load_facilities import AMENITY_TO_TYPE
        valid_types = {"hospital", "fire_station", "shelter"}
        for v in AMENITY_TO_TYPE.values():
            assert v in valid_types
