"""
backend/tests/test_routing_api.py — FastAPI endpoint integration tests.
Tests /api/health, /api/readiness, /api/study-areas, /api/facilities,
/api/scenarios, /api/routes, and /api/compare/routes with TestClient.
"""
import os
import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live API integration tests",
)


@pytest.fixture(scope="session")
def client():
    from backend.app.main import app
    return TestClient(app)


class TestHealthAndReadiness:
    def test_health_shallow(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "database_configured" in data

    @skip_no_db
    def test_readiness_deep(self, client):
        r = client.get("/api/readiness")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert "postgis" in data["extensions"]
        assert "pgrouting" in data["extensions"]
        assert data["tables_present"] >= 9


@skip_no_db
class TestStudyAreasAndFacilitiesEndpoints:
    def test_study_areas(self, client):
        r = client.get("/api/study-areas")
        assert r.status_code == 200
        areas = r.json()
        assert len(areas) >= 1
        assert areas[0]["name"] == "Downtown Houston Pilot"

    def test_facilities_all(self, client):
        r = client.get("/api/facilities?area_id=1")
        assert r.status_code == 200
        facs = r.json()
        assert len(facs) == 9

    def test_facilities_filter_by_type(self, client):
        r = client.get("/api/facilities?area_id=1&facility_type=hospital")
        assert r.status_code == 200
        hospitals = r.json()
        assert all(h["facility_type"] == "hospital" for h in hospitals)

    def test_facilities_filter_by_status_verified(self, client):
        r = client.get("/api/facilities?area_id=1&status=verified")
        assert r.status_code == 200
        verified = r.json()
        assert len(verified) == 3
        names = {v["name"] for v in verified}
        assert "Saint Joseph Medical Center" in names


@skip_no_db
class TestScenariosEndpoints:
    def test_scenarios_list(self, client):
        r = client.get("/api/scenarios?area_id=1")
        assert r.status_code == 200
        scs = r.json()
        assert len(scs) >= 2
        kinds = {s["scenario_kind"] for s in scs}
        assert "baseline" in kinds
        assert "hazard_polygon" in kinds

    def test_scenario_detail_hazard_polygon(self, client):
        # Scenario 2 is the hazard prototype
        r = client.get("/api/scenarios/2")
        assert r.status_code == 200
        data = r.json()
        assert data["scenario_kind"] == "hazard_polygon"
        assert data["affected_road_count"] >= 100
        assert "FEMA" in data["name"] or "SFHA" in data["name"]
        assert "modeling_rule" in data
        assert "disclaimer" in data

    def test_scenario_affected_roads_geojson(self, client):
        r = client.get("/api/scenarios/2/affected-roads")
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) >= 100
        first_feat = fc["features"][0]
        assert "flood_zone" in first_feat["properties"]
        assert "intersection_fraction" in first_feat["properties"]
        assert first_feat["geometry"]["type"] == "LineString"

    def test_nonexistent_scenario_returns_404(self, client):
        r = client.get("/api/scenarios/99999")
        assert r.status_code == 404


@skip_no_db
class TestRoutesEndpoint:
    def test_point_to_point_route_success(self, client):
        u, v = 151635251, 152272624
        r = client.get(f"/api/routes?origin_node_id={u}&destination_node_id={v}")
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is True
        assert data["travel_time_s"] > 0
        assert data["edge_count"] > 0
        assert data["geometry"] is not None
        assert data["geometry"]["type"] == "LineString"
        assert len(data["geometry"]["coordinates"]) >= 2

    def test_same_node_route_returns_zero(self, client):
        node = 151461824
        r = client.get(f"/api/routes?origin_node_id={node}&destination_node_id={node}")
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is True
        assert data["travel_time_s"] == 0.0
        assert data["edge_count"] == 0

    def test_unreachable_route_returns_reachable_false(self, client):
        r = client.get("/api/routes?origin_node_id=151461407&destination_node_id=152725875")
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is False
        assert data["travel_time_s"] is None

    def test_nearest_hospital_route(self, client):
        origin = 151461824
        r = client.get(f"/api/routes?origin_node_id={origin}&facility_type=hospital")
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is True
        assert data["facility"] is not None
        assert data["facility"]["name"] == "Saint Joseph Medical Center"
        assert data["travel_time_s"] > 0
        assert data["geometry"]["type"] == "LineString"

    def test_nearest_fire_station_route(self, client):
        origin = 151461824
        r = client.get(f"/api/routes?origin_node_id={origin}&facility_type=fire_station")
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is True
        assert data["facility"]["type"] == "fire_station"

    def test_missing_destination_and_facility_type_returns_422(self, client):
        r = client.get("/api/routes?origin_node_id=151461824")
        assert r.status_code == 422

    def test_negative_node_id_validation_error(self, client):
        r = client.get("/api/routes?origin_node_id=-5&destination_node_id=10")
        assert r.status_code == 422


@skip_no_db
class TestCompareRoutesEndpoint:
    def test_compare_routes_point_to_point(self, client):
        u, v = 151635251, 152272624
        r = client.get(f"/api/compare/routes?origin_node_id={u}&destination_node_id={v}&scenario_id=2")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("unaffected", "detoured", "isolated")
        assert "baseline" in data
        assert "disrupted" in data
        assert "modeling_disclaimer" in data

    def test_compare_routes_nearest_facility(self, client):
        origin = 151461824
        r = client.get(f"/api/compare/routes?origin_node_id={origin}&facility_type=hospital&scenario_id=2")
        assert r.status_code == 200
        data = r.json()
        assert "baseline" in data
        assert "disrupted" in data
        assert data["baseline"]["reachable"] is True


@skip_no_db
class TestAccessibilityEndpoints:
    def test_scenario_impact_baseline(self, client):
        r = client.get("/api/scenarios/1/impact?threshold_minutes=15")
        assert r.status_code == 200
        data = r.json()
        assert data["scenario_id"] == 1
        assert data["threshold_minutes"] == 15
        assert data["total_modeled_population"] == 740186
        assert data["reachable_population"] == 25790
        assert data["network_unreachable_population"] == 0
        assert data["invalid_snap_population"] == 714396
        assert data["population_losing_threshold_access"] == 0
        assert data["reconciliation"]["matches_total"] is True

    def test_scenario_impact_flood(self, client):
        r = client.get("/api/scenarios/2/impact?threshold_minutes=15")
        assert r.status_code == 200
        data = r.json()
        assert data["scenario_id"] == 2
        assert data["threshold_minutes"] == 15
        assert data["total_modeled_population"] == 740186
        assert data["reachable_population"] == 21496
        assert data["network_unreachable_population"] == 4294
        assert data["invalid_snap_population"] == 714396
        assert data["population_losing_threshold_access"] == 4294
        assert data["reconciliation"]["matches_total"] is True
        assert "modeling_disclaimer" in data

    def test_scenario_impact_invalid_threshold_returns_422(self, client):
        r = client.get("/api/scenarios/2/impact?threshold_minutes=1")
        assert r.status_code == 422

    def test_scenario_accessibility_origins_geojson(self, client):
        r = client.get("/api/scenarios/2/accessibility-origins?threshold_minutes=15")
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 548
        first = fc["features"][0]
        assert "origin_id" in first["properties"]
        assert "geoid" in first["properties"]
        assert "population" in first["properties"]
        assert "status_category" in first["properties"]
        assert first["geometry"]["type"] in ("Point", "MultiPoint")

