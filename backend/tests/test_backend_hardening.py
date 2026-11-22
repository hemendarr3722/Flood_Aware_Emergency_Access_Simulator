"""
backend/tests/test_backend_hardening.py — Phase 6 hardening and security tests.
Tests endpoint validation, bounding box enforcement, feature capping, SQL injection
resistance, error envelopes, and request ID tracking.
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


class TestRequestIdAndHeaders:
    def test_request_id_generated_and_returned(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert "x-request-id" in r.headers
        assert len(r.headers["x-request-id"]) > 0

    def test_client_request_id_echoed(self, client):
        custom_id = "test-request-id-12345"
        r = client.get("/api/health", headers={"x-request-id": custom_id})
        assert r.status_code == 200
        assert r.headers["x-request-id"] == custom_id


@skip_no_db
class TestStudyAreaSummaryEndpoint:
    def test_study_area_summary_success(self, client):
        r = client.get("/api/study-areas/1/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == 1
        assert data["name"] == "Downtown Houston Pilot"
        assert "bounds" in data
        assert data["bounds"]["min_lon"] < data["bounds"]["max_lon"]
        assert data["bounds"]["min_lat"] < data["bounds"]["max_lat"]

        metrics = data["metrics"]
        assert metrics["total_road_nodes"] == 468
        assert metrics["total_road_edges"] == 884
        assert metrics["total_road_length_km"] > 0
        assert metrics["total_facilities"] == 9
        assert metrics["verified_facilities"] == 3
        assert metrics["candidate_facilities"] == 3
        assert metrics["excluded_facilities"] == 3
        assert (
            metrics["verified_facilities"]
            + metrics["candidate_facilities"]
            + metrics["excluded_facilities"]
            == metrics["total_facilities"]
        )
        assert metrics["modeled_population"] == 740186
        assert metrics["snapped_pilot_population"] == 25790
        assert metrics["available_scenarios"] >= 2
        assert "disclaimer" in data

    def test_nonexistent_study_area_returns_404(self, client):
        r = client.get("/api/study-areas/99999/summary")
        assert r.status_code == 404
        data = r.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"


@skip_no_db
class TestRoadsBoundingAndFiltering:
    def test_roads_default_returns_features(self, client):
        r = client.get("/api/roads?area_id=1&limit=50")
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 50
        feat = fc["features"][0]
        assert "id" in feat["properties"]
        assert "is_closed" in feat["properties"]
        assert "state" in feat["properties"]

    def test_roads_valid_bbox(self, client):
        # Bounding box around Downtown Houston
        bbox = "-95.375,29.745,-95.350,29.765"
        r = client.get(f"/api/roads?area_id=1&bbox={bbox}&limit=500")
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) > 0

    def test_roads_bbox_too_large_returns_422(self, client):
        # Bbox exceeding 0.5 degrees
        large_bbox = "-96.0,29.0,-95.0,30.0"
        r = client.get(f"/api/roads?area_id=1&bbox={large_bbox}")
        assert r.status_code == 422
        data = r.json()
        assert "error" in data
        assert "exceeds maximum allowed span" in data["detail"]

    def test_roads_bbox_reversed_coords_returns_422(self, client):
        reversed_bbox = "-95.350,29.765,-95.375,29.745"
        r = client.get(f"/api/roads?area_id=1&bbox={reversed_bbox}")
        assert r.status_code == 422
        data = r.json()
        assert "strictly less than" in data["detail"]

    def test_roads_bbox_malformed_returns_422(self, client):
        r = client.get("/api/roads?area_id=1&bbox=-95.35,29.75")
        assert r.status_code == 422
        data = r.json()
        assert "exactly 4 comma-separated values" in data["detail"]

    def test_roads_state_closed_filtering(self, client):
        r = client.get("/api/roads?area_id=1&scenario_id=2&state=closed&limit=3000")
        assert r.status_code == 200
        fc = r.json()
        assert len(fc["features"]) == 124
        assert all(f["properties"]["is_closed"] is True for f in fc["features"])
        assert all(f["properties"]["state"] == "closed" for f in fc["features"])

    def test_roads_state_normal_filtering(self, client):
        r = client.get("/api/roads?area_id=1&scenario_id=2&state=normal&limit=3000")
        assert r.status_code == 200
        fc = r.json()
        assert len(fc["features"]) == 884 - 124  # 760 passable edges
        assert all(f["properties"]["is_closed"] is False for f in fc["features"])
        assert all(f["properties"]["state"] == "normal" for f in fc["features"])


class TestSecurityAndInjectionResistance:
    def test_sql_injection_in_bbox_rejected(self, client):
        malicious_bbox = "-95.35,29.75,-95.30); DROP TABLE gis.road_edges; --"
        r = client.get(f"/api/roads?area_id=1&bbox={malicious_bbox}")
        assert r.status_code == 422
        data = r.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_sql_injection_in_facility_type_rejected(self, client):
        malicious_type = "hospital' OR 1=1--"
        r = client.get(f"/api/facilities?area_id=1&facility_type={malicious_type}")
        assert r.status_code == 422

    def test_negative_id_rejected(self, client):
        r = client.get("/api/study-areas/-1/summary")
        assert r.status_code == 422

    def test_negative_scenario_id_rejected(self, client):
        r = client.get("/api/scenarios/-5")
        assert r.status_code == 422


class TestConsistentErrorEnvelope:
    def test_404_envelope_format(self, client):
        r = client.get("/api/scenarios/99999")
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data
        assert "error" in data
        err = data["error"]
        assert err["code"] == "HTTP_404"
        assert "not found" in err["message"].lower()
        assert "request_id" in err

    def test_422_envelope_format(self, client):
        r = client.get("/api/routes?origin_node_id=1")  # missing destination and facility_type
        assert r.status_code == 422
        data = r.json()
        assert "detail" in data
        assert "error" in data
        err = data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert "request_id" in err
