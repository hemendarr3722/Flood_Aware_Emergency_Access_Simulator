"""
database/tests/test_routing_baseline.py — Phase 3 Baseline Routing Validation Suite.

Validates:
1. Benchmark of >=10 sampled routes comparing pgRouting against NetworkX reference graph.
2. Topological continuity: each edge in the returned path connects to the next edge in route order.
3. Cost reconciliation: route aggregate cost equals sum of individual edge costs.
4. One-way street direction enforcement (reverse cost = -1).
5. Same-node routes: travel time is zero, reachable is true.
6. Disconnected / unreachable node pairs: controlled unreachable response, no crash.
7. Nearest reachable facility routing using one-to-many pgRouting Dijkstra.
8. Facility curation: verified acute emergency facilities vs excluded outpatient/admin facilities.
9. Baseline scenario representation in gis.flood_scenarios.

Usage:
    pytest database/tests/test_routing_baseline.py -v
"""
from __future__ import annotations
import os
import pytest
import networkx as nx
import osmnx as ox
from pathlib import Path
from psycopg import connect
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("DATABASE_URL")
GRAPHML_PATH = ROOT / "data" / "raw" / "osm" / "drive_network.graphml"

skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live routing integration tests",
)


@pytest.fixture(scope="session")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    with connect(DATABASE_URL, row_factory=dict_row) as c:
        yield c


@pytest.fixture(scope="session")
def graph():
    if not GRAPHML_PATH.exists():
        pytest.skip(f"GraphML not found at {GRAPHML_PATH}")
    return ox.load_graphml(GRAPHML_PATH)


@skip_no_db
class TestRouteBenchmarkNetworkX:
    """Benchmark >= 10 sampled routes against NetworkX Dijkstra on the reference graph."""

    def test_ten_benchmark_routes_match_networkx(self, conn, graph):
        nodes = list(graph.nodes)
        benchmark_pairs = []

        # Find 10 diverse reachable pairs across the graph
        for i, u in enumerate(nodes[::15]):
            for v in nodes[i + 5::12]:
                if u != v and nx.has_path(graph, u, v):
                    benchmark_pairs.append((u, v))
                    if len(benchmark_pairs) >= 12:
                        break
            if len(benchmark_pairs) >= 12:
                break

        assert len(benchmark_pairs) >= 10, f"Expected >= 10 reachable benchmark pairs, found {len(benchmark_pairs)}"

        results = []
        for u, v in benchmark_pairs:
            # NetworkX reference
            nx_time = nx.shortest_path_length(graph, u, v, weight="travel_time")
            nx_path = nx.shortest_path(graph, u, v, weight="travel_time")

            # pgRouting via database
            rows = conn.execute(
                "select seq, path_seq, node, edge, cost, agg_cost from gis.route_edges(%s, %s)",
                (u, v),
            ).fetchall()

            assert len(rows) > 0, f"pgRouting returned no path for reachable pair ({u}, {v})"
            pgr_time = rows[-1]["agg_cost"]
            pgr_nodes = [r["node"] for r in rows]

            # Invariant: travel times match within 0.05 seconds
            diff = abs(nx_time - pgr_time)
            results.append({
                "origin": u,
                "dest": v,
                "nx_nodes": len(nx_path),
                "pgr_nodes": len(pgr_nodes),
                "nx_time_s": nx_time,
                "pgr_time_s": pgr_time,
                "diff_s": diff,
            })
            assert diff <= 0.05, f"Route {u}->{v} cost mismatch: NX={nx_time:.4f}s vs PGR={pgr_time:.4f}s (diff={diff:.4f}s)"

        print(f"\n--- BENCHMARK RESULTS ({len(results)} routes) ---")
        for r in results:
            print(f"  {r['origin']} -> {r['dest']}: "
                  f"nodes={r['pgr_nodes']}, time={r['pgr_time_s']:.2f}s, diff={r['diff_s']:.4f}s")


@skip_no_db
class TestRouteCorrectnessInvariants:
    """Verify core routing invariants required by master prompt."""

    def test_same_node_travel_time_is_zero(self, conn):
        sample_node = conn.execute("select id from gis.road_nodes limit 1").fetchone()["id"]
        rows = conn.execute(
            "select seq, path_seq, node, edge, cost, agg_cost from gis.route_edges(%s, %s)",
            (sample_node, sample_node),
        ).fetchall()
        # In pgRouting, same-node query returns 0 rows or 1 row with cost=0
        if rows:
            assert rows[0]["cost"] == 0.0
            assert rows[0]["agg_cost"] == 0.0

    def test_topological_continuity_route_edges(self, conn, graph):
        """Every returned edge connects to the next edge in route order."""
        # Pick a multi-hop route
        u, v = 151461824, 151903119
        rows = conn.execute(
            """
            select
                d.seq, d.path_seq, d.node, d.edge, d.cost, d.agg_cost,
                e.source, e.target, e.length_m
            from gis.route_edges(%s, %s) d
            left join gis.road_edges e on e.id = d.edge
            order by d.path_seq asc
            """,
            (u, v),
        ).fetchall()

        edges = [r for r in rows if r["edge"] >= 0]
        assert len(edges) >= 3, "Expected multi-hop route"

        for i in range(len(edges) - 1):
            assert edges[i]["target"] == edges[i + 1]["source"], (
                f"Topological break at step {i}: "
                f"edge {edges[i]['edge']} target={edges[i]['target']} != "
                f"edge {edges[i+1]['edge']} source={edges[i+1]['source']}"
            )

    def test_aggregate_cost_equals_sum_of_edge_costs(self, conn):
        """Route aggregate cost equals the sum of edge costs within floating-point tolerance."""
        u, v = 151461824, 151903119
        rows = conn.execute(
            "select edge, cost, agg_cost from gis.route_edges(%s, %s)",
            (u, v),
        ).fetchall()

        edge_costs_sum = sum(r["cost"] for r in rows if r["edge"] >= 0)
        final_agg_cost = rows[-1]["agg_cost"]
        assert abs(edge_costs_sum - final_agg_cost) < 1e-4, (
            f"Cost sum mismatch: sum={edge_costs_sum} vs agg={final_agg_cost}"
        )

    def test_one_way_restrictions_enforced(self, conn):
        """Reversing a one-way edge must not allow backward traversal."""
        # Find an edge that is strictly one-way (reverse_cost_s = -1)
        one_way = conn.execute(
            "select id, source, target, cost_s, reverse_cost_s from gis.road_edges "
            "where reverse_cost_s = -1 and not exists ("
            "  select 1 from gis.road_edges r where r.source = road_edges.target and r.target = road_edges.source"
            ") limit 1"
        ).fetchone()

        if one_way:
            u, v = one_way["source"], one_way["target"]
            # Forward route should be direct (1 edge)
            fwd = conn.execute(
                "select edge, agg_cost from gis.route_edges(%s, %s)", (u, v)
            ).fetchall()
            assert len(fwd) > 0, "Forward path must exist"

            # Reverse direct traversal: v -> u should NOT be a 1-hop path on the same edge
            rev = conn.execute(
                "select edge, agg_cost from gis.route_edges(%s, %s)", (v, u)
            ).fetchall()
            rev_edges = [r["edge"] for r in rev if r["edge"] >= 0]
            # Edge must not be traversed in reverse
            assert one_way["id"] not in rev_edges, "One-way edge was traversed in reverse!"
            if rev:
                # If a detour path exists, it must be strictly longer/slower than forward
                assert rev[-1]["agg_cost"] > fwd[-1]["agg_cost"], "Reverse detour should be longer than direct forward"

    def test_unreachable_node_pair_returns_empty(self, conn):
        """Fringe node with no path to target returns empty result gracefully."""
        # 151461407 cannot reach hospital 152725875 in one-way grid
        rows = conn.execute(
            "select * from gis.route_edges(%s, %s)",
            (151461407, 152725875),
        ).fetchall()
        assert len(rows) == 0, "Unreachable pair should return 0 rows from route_edges"

    def test_invalid_node_id_handled_safely(self, conn):
        """Nonexistent node IDs return 0 rows without raising database errors."""
        rows = conn.execute(
            "select * from gis.route_edges(%s, %s)",
            (-999999, 99999999999),
        ).fetchall()
        assert len(rows) == 0


@skip_no_db
class TestNearestFacilityRouting:
    """Verify one-to-many nearest reachable emergency facility routing."""

    def test_nearest_hospital_routing(self, conn):
        # Origin node in downtown
        origin = 151461824
        res = conn.execute(
            "select * from gis.route_nearest_facility(%s, 'hospital', null)",
            (origin,),
        ).fetchall()

        assert len(res) == 1, "Should find exactly 1 nearest reachable hospital"
        fac = res[0]
        assert fac["facility_name"] == "Saint Joseph Medical Center"
        assert fac["facility_type"] == "hospital"
        assert fac["total_travel_time_s"] > 0
        assert fac["edge_count"] > 0
        assert len(fac["path_edges"]) == fac["edge_count"]

    def test_nearest_fire_station_routing(self, conn):
        origin = 151461824
        res = conn.execute(
            "select * from gis.route_nearest_facility(%s, 'fire_station', null)",
            (origin,),
        ).fetchall()

        assert len(res) == 1, "Should find nearest fire station"
        fac = res[0]
        assert fac["facility_type"] == "fire_station"
        assert fac["total_travel_time_s"] > 0

    def test_same_node_nearest_facility(self, conn):
        """When origin is already at the facility node, travel time must be 0."""
        # Saint Joseph Medical Center node
        hospital_node = 152725875
        res = conn.execute(
            "select * from gis.route_nearest_facility(%s, 'hospital', null)",
            (hospital_node,),
        ).fetchall()

        assert len(res) == 1
        fac = res[0]
        assert fac["total_travel_time_s"] == 0.0
        assert fac["edge_count"] == 0


@skip_no_db
class TestFacilityCuration:
    """Verify candidate/verified/excluded status and documented reasons."""

    def test_verified_facilities_exist(self, conn):
        verified = conn.execute(
            "select name, facility_type, validation_status, snap_distance_m "
            "from gis.facilities where validation_status = 'verified'"
        ).fetchall()
        names = {r["name"] for r in verified}
        assert "Saint Joseph Medical Center" in names
        assert "Houston Fire Department Station 8" in names
        assert "Houston Police Department" in names
        # Snap distances must be reasonable (< 100m)
        for r in verified:
            assert r["snap_distance_m"] < 100.0, f"Verified facility {r['name']} snap distance too large"

    def test_excluded_facilities_have_documented_reasons(self, conn):
        excluded = conn.execute(
            "select name, exclusion_reason, is_active "
            "from gis.facilities where validation_status = 'excluded'"
        ).fetchall()
        assert len(excluded) >= 3, "Expected at least 3 excluded facilities"
        for r in excluded:
            assert not r["is_active"], f"Excluded facility {r['name']} should be is_active=false"
            assert r["exclusion_reason"] is not None and len(r["exclusion_reason"]) > 10, (
                f"Excluded facility {r['name']} missing detailed reason"
            )


@skip_no_db
class TestBaselineScenarioRepresentation:
    """Verify baseline scenario representation in flood_scenarios."""

    def test_baseline_scenario_exists(self, conn):
        row = conn.execute(
            "select id, name, scenario_kind, threshold_m, status "
            "from gis.flood_scenarios where scenario_kind = 'baseline'"
        ).fetchone()
        assert row is not None, "Baseline scenario not found in gis.flood_scenarios"
        assert row["status"] == "ready"
        assert row["threshold_m"] == 0.0

    def test_baseline_has_no_closed_edges(self, conn):
        """Baseline scenario must have zero closed edges in scenario_edge_impacts."""
        scenario_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'baseline'"
        ).fetchone()["id"]
        row = conn.execute(
            "select count(*) cnt from gis.scenario_edge_impacts "
            "where scenario_id = %s and is_closed = true",
            (scenario_id,),
        ).fetchone()
        assert row["cnt"] == 0, "Baseline scenario must not have closed edges"
