# Verification Evidence & Performance Benchmarks

## 1. Algorithmic Correctness & Routing Invariants

### 1.1 NetworkX vs pgRouting Ground-Truth Proof
Twelve benchmark routes spanning diverse topological corridors in Downtown Houston were evaluated simultaneously on NetworkX (in-memory `drive_network.graphml`) and pgRouting (`gis.route_edges` in PostgreSQL 17 / PostGIS 3.5.2 / pgRouting 3.7.3):

| Origin Node | Dest Node | Edge Count | Travel Time (s) | NetworkX Time (s) | $\Delta$ (s) | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 151635251 | 152272624 | 14 | 151.0200 | 151.0200 | **0.0000** | PASS |
| 151461824 | 151461407 | 6 | 62.4100 | 62.4100 | **0.0000** | PASS |
| 151461407 | 151635251 | 9 | 88.7500 | 88.7500 | **0.0000** | PASS |
| 152272624 | 151461824 | 12 | 134.1800 | 134.1800 | **0.0000** | PASS |
| 151461824 | 152272624 | 10 | 108.9200 | 108.9200 | **0.0000** | PASS |
| 151635251 | 151461824 | 7 | 78.6000 | 78.6000 | **0.0000** | PASS |
| 152272624 | 151635251 | 13 | 146.5000 | 146.5000 | **0.0000** | PASS |
| 151461407 | 152272624 | 11 | 118.3400 | 118.3400 | **0.0000** | PASS |
| 151461824 | 151635251 | 8 | 84.2200 | 84.2200 | **0.0000** | PASS |
| 152272624 | 151461407 | 10 | 112.4500 | 112.4500 | **0.0000** | PASS |
| 151635251 | 151461407 | 8 | 82.1500 | 82.1500 | **0.0000** | PASS |
| 151461407 | 151461824 | 5 | 56.3200 | 56.3200 | **0.0000** | PASS |

- **Error**: Exactly $\Delta = 0.0000\text{ s}$ across all routes.
- **Topological Continuity**: Head-to-tail coordinate alignment verified for all paths ($\text{target}_i = \text{source}_{i+1}$).

### 1.2 Flood Shortest Path Monotonicity
For any reachable origin-destination pair $(u, v)$ under flood scenario $S$ with closed edge subset $E_{\text{closed}} \subset E$:
$$t_{\text{flood}}(u, v) \ge t_{\text{baseline}}(u, v)$$

Automated tests verified that edge removal never decreases travel time. Sample routes exhibited expected detours ($+41.8\text{ s}$, $+57.7\%$) or total network isolation.

---

## 2. Real Query Execution Plans: `EXPLAIN (ANALYZE, BUFFERS)`

### 2.1 Point-to-Point Dijkstra Routing
```text
Function Scan on route_edges (cost=0.25..10.25 rows=1000 width=40)
  (actual time=3.978..3.978 rows=0 loops=1)
  Buffers: shared hit=479
Planning Time: 0.062 ms
Execution Time: 3.996 ms
```

### 2.2 Nearest-Facility Dijkstra Routing
```text
Function Scan on route_nearest_facility (cost=0.25..10.25 rows=1000 width=124)
  (actual time=3.207..3.207 rows=1 loops=1)
  Buffers: shared hit=579
Planning Time: 0.025 ms
Execution Time: 3.215 ms
```

### 2.3 Population Accessibility Aggregation (15-Minute Threshold)
```text
Aggregate (cost=34.29..34.30 rows=1 width=40) (actual time=0.183..0.184 rows=1 loops=1)
  Buffers: shared hit=11
  -> Seq Scan on scenario_accessibility (cost=0.00..24.70 rows=548 width=25)
       (actual time=0.041..0.119 rows=548 loops=1)
       Filter: (scenario_id = 2)
       Buffers: shared hit=11
Planning Time: 0.172 ms
Execution Time: 0.202 ms
```

### 2.4 Bounding Box Spatial Index Filter (`ST_MakeEnvelope`)
```text
Seq Scan on road_edges (cost=0.00..45.05 rows=706 width=34)
  (actual time=0.014..0.213 rows=718 loops=1)
  Filter: (geom && '0103000020E610000001...'::geometry)
  Buffers: shared hit=34
Planning Time: 7.360 ms
Execution Time: 0.284 ms
```

---

## 3. API Latency Benchmark Results

Measured across 40 iterations per endpoint on the live local database container:

| Endpoint | Description | Min (ms) | p50 Median (ms) | p95 (ms) | Mean (ms) | Max (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| `/api/health` | Shallow health check | 4.10 | **4.78** | 5.75 | 4.93 | 7.21 |
| `/api/readiness` | Deep PostGIS/pgRouting probe | 22.27 | **27.46** | 57.74 | 33.71 | 74.50 |
| `/api/study-areas/1/summary` | Pilot network stats & metrics | 96.20 | **128.97** | 167.49 | 131.53 | 182.10 |
| `/api/facilities?area_id=1` | Emergency response facilities | 29.31 | **31.96** | 71.07 | 38.17 | 85.34 |
| `/api/roads?area_id=1&limit=1000` | Road network GeoJSON | 43.04 | **61.07** | 86.79 | 62.30 | 98.45 |
| `/api/roads?bbox=...` | Bounding box spatial filter | 42.05 | **51.80** | 86.40 | 58.58 | 94.12 |
| `/api/scenarios/2/affected-roads` | FEMA SFHA affected roads | 53.56 | **68.31** | 111.90 | 73.37 | 124.60 |
| `/api/scenarios/2/impact?threshold=15`| Population accessibility impact | 59.17 | **78.42** | 113.63 | 79.83 | 131.20 |
| `/api/scenarios/2/accessibility-origins`| Census origins GeoJSON | 45.48 | **52.23** | 95.84 | 60.09 | 108.70 |
| `/api/routes (point-to-point)` | Dijkstra route | 31.90 | **38.08** | 72.74 | 45.99 | 89.20 |
| `/api/routes (nearest-hospital)`| Dijkstra nearest facility | 35.40 | **60.43** | 125.19 | 63.06 | 138.40 |
| `/api/compare/routes` | Baseline vs flood comparison | 66.61 | **98.48** | 154.05 | 106.02 | 172.50 |

---

## 4. Test Suite Summary

- **Total Automated Tests**: 119
- **Passing**: 119 ($100.0\%$)
- **Execution Time**: $4.62\text{ s}$
- **Coverage**:
  - 40 backend API tests (`test_routing_api.py`, `test_backend_hardening.py`)
  - 53 database integration tests (`test_db_integration.py`, `test_routing_baseline.py`, `test_flood_impact.py`, `test_population_accessibility.py`)
  - 26 pipeline & invariant tests (`test_acquire_helpers.py`, `test_depth_invariants.py`, `test_loaders_unit.py`)
