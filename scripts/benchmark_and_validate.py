"""
scripts/benchmark_and_validate.py — Phase 8 performance benchmarking & EXPLAIN ANALYZE validation.
Runs real EXPLAIN (ANALYZE, BUFFERS) on routing queries and measures API latency (p50, p95).
"""
import os
import time
import json
import statistics
from fastapi.testclient import TestClient

def run_db_explains():
    from backend.app.core.database import db
    print("=" * 60)
    print("1. RUNNING EXPLAIN (ANALYZE, BUFFERS) ON CORE QUERIES")
    print("=" * 60)

    with db() as conn:
        # Query 1: Point-to-point Dijkstra
        print("\n--- Query 1: Point-to-point Dijkstra (Node 151635251 -> 152272624) ---")
        q1 = "EXPLAIN (ANALYZE, BUFFERS) select * from gis.route_edges(151635251, 152272624, 2)"
        rows1 = conn.execute(q1).fetchall()
        for r in rows1:
            print(list(r.values())[0])

        # Query 2: Nearest Facility Dijkstra (Origin 151461824 -> Nearest Hospital)
        print("\n--- Query 2: Nearest Facility Dijkstra (Origin 151461824 -> Hospital) ---")
        q2 = "EXPLAIN (ANALYZE, BUFFERS) select * from gis.route_nearest_facility(151461824, 'hospital', 2)"
        rows2 = conn.execute(q2).fetchall()
        for r in rows2:
            print(list(r.values())[0])

        # Query 3: Scenario Accessibility Aggregation (15-min threshold)
        print("\n--- Query 3: Scenario Accessibility Impact Aggregation ---")
        q3 = """
        EXPLAIN (ANALYZE, BUFFERS)
        select
            count(*) as total_origins,
            sum(population) as total_pop,
            sum(population) filter (where reachable and travel_time_s <= 900) as within_15min,
            sum(population) filter (where status_category = 'network_unreachable') as unreachable_pop,
            percentile_cont(0.5) within group (order by travel_time_s) as median_s
        from gis.scenario_accessibility
        where scenario_id = 2
        """
        rows3 = conn.execute(q3).fetchall()
        for r in rows3:
            print(list(r.values())[0])

        # Query 4: Spatial Index Bounding Box Filter
        print("\n--- Query 4: Spatial Index Bounding Box Filter on road_edges ---")
        q4 = """
        EXPLAIN (ANALYZE, BUFFERS)
        select id, highway_class, length_m, cost_s
        from gis.road_edges
        where geom && ST_MakeEnvelope(-95.375, 29.745, -95.350, 29.765, 4326)
        """
        rows4 = conn.execute(q4).fetchall()
        for r in rows4:
            print(list(r.values())[0])

def run_api_benchmarks(n_iterations: int = 40):
    from backend.app.main import app
    client = TestClient(app)

    print("\n" + "=" * 60)
    print(f"2. API ENDPOINT LATENCY BENCHMARK ({n_iterations} iterations per endpoint)")
    print("=" * 60)

    endpoints = [
        ("Health (shallow)", "/api/health"),
        ("Readiness (deep db)", "/api/readiness"),
        ("Study Area Summary", "/api/study-areas/1/summary"),
        ("Facilities List", "/api/facilities?area_id=1&status=all"),
        ("Roads (1000 features)", "/api/roads?area_id=1&limit=1000"),
        ("Roads (Bbox filter)", "/api/roads?area_id=1&bbox=-95.375,29.745,-95.350,29.765"),
        ("Affected Roads (SFHA)", "/api/scenarios/2/affected-roads"),
        ("Scenario Impact (15m)", "/api/scenarios/2/impact?threshold_minutes=15"),
        ("Accessibility Origins", "/api/scenarios/2/accessibility-origins?threshold_minutes=15"),
        ("Point-to-Point Route", "/api/routes?origin_node_id=151635251&destination_node_id=152272624&scenario_id=2"),
        ("Nearest Hospital Route", "/api/routes?origin_node_id=151461824&facility_type=hospital&scenario_id=2"),
        ("Compare Routes", "/api/compare/routes?origin_node_id=151635251&destination_node_id=152272624&scenario_id=2"),
    ]

    results = []
    for name, path in endpoints:
        latencies = []
        # Warmup
        client.get(path)

        for _ in range(n_iterations):
            t0 = time.perf_counter()
            r = client.get(path)
            t1 = time.perf_counter()
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            latencies.append((t1 - t0) * 1000.0) # in ms

        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        min_l = min(latencies)
        max_l = max(latencies)
        mean_l = statistics.mean(latencies)

        results.append({
            "name": name,
            "path": path,
            "min_ms": round(min_l, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "mean_ms": round(mean_l, 2),
            "max_ms": round(max_l, 2),
        })

        print(f"  {name:<26} | min: {min_l:5.2f}ms | p50: {p50:5.2f}ms | p95: {p95:5.2f}ms | mean: {mean_l:5.2f}ms")

    with open("docs/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nBenchmark results saved to docs/benchmark_results.json")

if __name__ == "__main__":
    run_db_explains()
    run_api_benchmarks(n_iterations=40)
