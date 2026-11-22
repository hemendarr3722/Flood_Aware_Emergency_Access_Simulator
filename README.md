# Flood-Aware Emergency Access Simulator — Houston Pilot

A production-grade GIS emergency planning and accessibility simulation platform. Models how severe urban flood hazard events disrupt road networks and emergency response reachability (EMS, Fire, Medical) across Downtown Houston.

Built with **PostGIS 3.5**, **pgRouting 3.7**, **FastAPI** (Python 3.12), and **React 19** with **MapLibre GL 5**.

---

## 1. System Architecture

```mermaid
flowchart LR
    A["Raw Data Ingestion\n(OSM, FEMA NFHL, US Census ACS)"] --> B["PostGIS & pgRouting\n(Private gis schema, UTM Zone 15N)"]
    B --> C["FastAPI Service\n(Layered repos, BBox guards, RFC 7946 GeoJSON)"]
    C --> D["React 19 & MapLibre GL 5\n(Carto Positron, Accessibility choropleths, Detour analysis)"]
```

- **Database**: Local Dockerized PostGIS 3.5.2 + pgRouting 3.7.3 (`gis` private schema, RLS enabled on all 10 tables, `SECURITY INVOKER` routing functions).
- **Backend API**: Modular FastAPI service separating route handlers, repository SQL, Pydantic schemas, and structured request ID tracking.
- **Frontend UI**: Single-page MapLibre application rendering GPU-accelerated road layers, FEMA hazard closures, curated facility pins, Census origin accessibility markers, and interactive baseline vs flood detour comparison.
- **Safety Governance**: Prominently labeled as a municipal planning tool. Track B depth raster routing is disabled under a documented data blocker (0 sites in USGS FIM catalog).

---

## 2. Key Metrics & Verification Evidence

- **119 Automated Tests**: 100% passing across backend, database, and ETL invariant suites.
- **Routing Accuracy**: Verified 12 benchmark routes with **$\Delta = 0.0000\text{ s}$ error** against NetworkX on `drive_network.graphml`.
- **Query Latency**:
  - Point-to-point Dijkstra (`pgr_dijkstra`): **3.99 ms** execution time.
  - Nearest-facility Dijkstra: **3.21 ms** execution time.
  - All-origins accessibility aggregation: **0.20 ms** execution time.
- **Network Dimensions**: 468 nodes, 884 directed edges, 107.8 km road network.
- **Curated Facilities**: 3 verified (Saint Joseph Medical Center, HFD Station 8, HPD Central Patrol), 3 candidate, 3 excluded (documented reasons).
- **FEMA Flood Impact**: 124 road edges ($14.0\%$, $15.1\text{ km}$) intersect FEMA 100-year SFHA zones and are modeled as potentially affected in Scenario 2.
- **Population Reconciliation**: 548 Census block groups, 740,186 total population ($100.0\%$ reconciled, zero double-counting).
  - Baseline (Scenario 1): 25,790 within 15 min, 0 unreachable, 714,396 invalid snap ($>500\text{ m}$).
  - Flood (Scenario 2): 21,496 within 15 min, 4,294 network-unreachable, 714,396 invalid snap.
  - **Population losing access under flood**: Exactly **4,294 residents** isolated in Downtown Houston.

---

## 3. Local Setup & Reproduction

### Prerequisites
- Docker (for local PostgreSQL / PostGIS / pgRouting container)
- Python 3.12+
- Node.js 20+ and npm

### 3.1 Start Local Database Container
```powershell
docker run -d `
  --name flood_aware_postgis `
  -e POSTGRES_DB=flood_aware `
  -e POSTGRES_USER=flood_user `
  -e POSTGRES_PASSWORD=flood_local_dev_only `
  -p 15432:5432 `
  pgrouting/pgrouting:latest
```

### 3.2 Apply Schema Migrations
```powershell
$env:DATABASE_URL = "postgresql://flood_user:flood_local_dev_only@localhost:15432/flood_aware"

Get-Content database/migrations/001_local.sql | psql $env:DATABASE_URL
Get-Content database/migrations/002_local.sql | psql $env:DATABASE_URL
Get-Content database/migrations/003_routing_and_facilities.sql | psql $env:DATABASE_URL
Get-Content database/migrations/004_accessibility_schema.sql | psql $env:DATABASE_URL
```

### 3.3 Execute Idempotent Loaders & Analyzers
```powershell
.venv\Scripts\python.exe pipelines/load/run_all_loaders.py --confirm-write
.venv\Scripts\python.exe pipelines/transform/compute_hazard_impacts.py --area-id 1 --confirm-write
.venv\Scripts\python.exe pipelines/analyze/compute_population_accessibility.py --area-id 1 --confirm-write
```

### 3.4 Run Test Suite (119 Tests)
```powershell
.venv\Scripts\python.exe -m pytest backend/tests database/tests pipelines/tests -v
```

### 3.5 Start Backend API Service
```powershell
$env:DATABASE_URL = "postgresql://flood_user:flood_local_dev_only@localhost:15432/flood_aware"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000 --reload
```
Interactive OpenAPI documentation: `http://localhost:8000/docs`

### 3.6 Run Frontend UI
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 4. Documentation Index

- [Architecture & Design Details](file:///docs/architecture.md)
- [Data Dictionary & Table Specifications](file:///docs/data_dictionary.md)
- [Data Provenance & Modeling Methodology](file:///docs/provenance_and_methodology.md)
- [Verification Evidence & Performance Benchmarks](file:///docs/validation_and_benchmarks.md)
- [Safety Governance & Limitations](file:///docs/limitations_and_ethics.md)
- [Portfolio & Technical Interview Guide](file:///docs/interview_talking_points.md)

---

## 5. Ethical & Planning Disclaimers

> [!WARNING]
> Modeled potentially affected roads represent regulatory 100-year Special Flood Hazard Area (SFHA) boundaries from FEMA NFHL, **NOT** verified live flood observations or depth sensors.
> 
> This prototype is designed exclusively for municipal emergency planning, resource allocation studies, and infrastructure vulnerability modeling. **NEVER use for operational 911 dispatch, tactical emergency navigation, or consumer evacuation guidance.**
