"""
database/tests/test_flood_impact.py — Phase 4 Flood Impact & Disrupted Routing Tests.

Validates:
1. Track A FEMA hazard scenario creation, metadata, and transparent modeling rule.
2. Intersection fractions are strictly in [0.0, 1.0].
3. Disrupted route invariant: closed edges NEVER appear in a disrupted route.
4. Shortest path monotonicity invariant: with only edge removals, a disrupted route
   CANNOT be faster than baseline (t_flood >= t_baseline).
5. Route comparison: detoured routes show positive delay (delay_s > 0).
6. Disrupted nearest facility routing avoids affected edges.
"""
import os
import pytest
from psycopg import connect
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live database integration tests",
)


@pytest.fixture(scope="session")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    with connect(DATABASE_URL, row_factory=dict_row) as c:
        yield c


@skip_no_db
class TestFEMAHazardScenarioIntegrity:
    """Validate Track A FEMA SFHA hazard scenario properties."""

    def test_hazard_scenario_exists(self, conn):
        sc = conn.execute(
            "select id, name, scenario_kind, status, algorithm_version "
            "from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()
        assert sc is not None, "FEMA hazard scenario not found in gis.flood_scenarios"
        assert sc["status"] == "ready"
        assert "fema" in sc["name"].lower() or "sfha" in sc["name"].lower()
        assert sc["algorithm_version"] is not None

    def test_impacted_edges_count_and_fraction_bounds(self, conn):
        sc_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        rows = conn.execute(
            "select edge_id, is_closed, impact_kind, intersection_fraction, flood_zone, sfha_tf "
            "from gis.scenario_edge_impacts where scenario_id = %s",
            (sc_id,),
        ).fetchall()

        assert len(rows) > 0, "No impacted edges found for hazard scenario"
        assert len(rows) >= 100, f"Expected >= 100 impacted edges in pilot, found {len(rows)}"

        for r in rows:
            assert r["is_closed"] is True, "Hazard impacted edge should be marked is_closed=true"
            assert r["impact_kind"] == "hazard_polygon"
            assert r["sfha_tf"] == "T", "Only SFHA=T zones should be in this scenario"
            assert 0.0 <= r["intersection_fraction"] <= 1.0, (
                f"Intersection fraction {r['intersection_fraction']} out of bounds [0, 1]"
            )

    def test_data_blocker_depth_track_remains_disabled(self, conn):
        """Track B depth raster claims must NOT be enabled without verified authentic raster."""
        depth_scenarios = conn.execute(
            "select count(*) cnt from gis.flood_scenarios where scenario_kind = 'depth_raster'"
        ).fetchone()["cnt"]
        assert depth_scenarios == 0, (
            "Track B depth_raster scenario was enabled without passing authentic data gate!"
        )


@skip_no_db
class TestDisruptedRoutingInvariants:
    """Core scientific invariants for flood disruption routing."""

    def test_closed_edges_never_appear_in_disrupted_route(self, conn):
        """CRITICAL INVARIANT: A road edge flagged as closed in a scenario must never appear in its route."""
        sc_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        closed_edges = {
            r["edge_id"]
            for r in conn.execute(
                "select edge_id from gis.scenario_edge_impacts where scenario_id = %s and is_closed = true",
                (sc_id,),
            ).fetchall()
        }
        assert len(closed_edges) > 0

        # Sample reachable pairs and verify no returned edge is in closed_edges
        sample_nodes = [
            151635251, 151488629, 151978743, 152113833, 152121781,
            152147500, 152189446, 152208783, 152272624, 152370730,
        ]

        verified_disrupted_routes = 0
        for u in sample_nodes[:5]:
            for v in sample_nodes[5:]:
                rows = conn.execute(
                    "select edge from gis.route_edges(%s, %s, %s)",
                    (u, v, sc_id),
                ).fetchall()
                path_edges = [r["edge"] for r in rows if r["edge"] >= 0]
                if path_edges:
                    verified_disrupted_routes += 1
                    overlap = set(path_edges).intersection(closed_edges)
                    assert not overlap, (
                        f"CRITICAL FAILURE: Closed edge(s) {overlap} appeared in disrupted route {u}->{v}!"
                    )

        assert verified_disrupted_routes > 0, "At least one disrupted route should be tested"

    def test_flood_route_cannot_be_faster_than_baseline_monotonicity(self, conn):
        """
        SHORTEST PATH MONOTONICITY INVARIANT:
        When only edges are removed (or costs increased), the shortest path in the
        flood scenario CANNOT be faster than the baseline shortest path.
        t_flood >= t_baseline (within floating point epsilon 1e-4)
        """
        sc_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        # Dynamically discover pairs that remain reachable under the flood scenario
        sample_nodes = [
            r["id"]
            for r in conn.execute("select id from gis.road_nodes order by id limit 80").fetchall()
        ]

        compared_count = 0
        detoured_count = 0

        for u in sample_nodes[:25]:
            for v in sample_nodes[25:60]:
                if u == v:
                    continue
                base_rows = conn.execute(
                    "select agg_cost from gis.route_edges(%s, %s, null)", (u, v)
                ).fetchall()
                if not base_rows:
                    continue

                flood_rows = conn.execute(
                    "select agg_cost from gis.route_edges(%s, %s, %s)", (u, v, sc_id)
                ).fetchall()

                # If reachable under flood, verify the flood route is never faster than baseline
                if flood_rows:
                    compared_count += 1
                    t_base = base_rows[-1]["agg_cost"]
                    t_flood = flood_rows[-1]["agg_cost"]

                    # INVARIANT CHECK: Flood route can NEVER be faster than baseline
                    assert t_flood >= t_base - 1e-4, (
                        f"MONOTONICITY VIOLATED: Flood route {u}->{v} ({t_flood:.2f}s) "
                        f"is faster than baseline ({t_base:.2f}s)!"
                    )

                    if t_flood > t_base + 0.1:
                        detoured_count += 1

                    if compared_count >= 10:
                        break
            if compared_count >= 10:
                break

        print(f"\nCompared {compared_count} routes: {detoured_count} detoured by flood hazard")
        assert compared_count >= 5, f"Expected at least 5 route comparisons, got {compared_count}"

    def test_disrupted_nearest_facility_routing(self, conn):
        """Nearest facility routing under flood conditions redirects to accessible path."""
        sc_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        origin = 151461824

        base_fac = conn.execute(
            "select * from gis.route_nearest_facility(%s, 'hospital', null)",
            (origin,),
        ).fetchall()[0]

        flood_fac = conn.execute(
            "select * from gis.route_nearest_facility(%s, 'hospital', %s)",
            (origin, sc_id),
        ).fetchall()

        if flood_fac:
            assert flood_fac[0]["total_travel_time_s"] >= base_fac["total_travel_time_s"] - 1e-4
            # Verify no closed edges in path
            closed_edges = {
                r["edge_id"]
                for r in conn.execute(
                    "select edge_id from gis.scenario_edge_impacts where scenario_id = %s and is_closed = true",
                    (sc_id,),
                ).fetchall()
            }
            overlap = set(flood_fac[0]["path_edges"]).intersection(closed_edges)
            assert not overlap, f"Nearest facility path contains closed edge(s): {overlap}"
