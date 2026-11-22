# System Architecture & Technical Design

## 1. High-Level System Overview

```mermaid
flowchart TD
    subgraph DataIngestion ["1. Data Acquisition & Transform (Pipelines)"]
        OSM["OpenStreetMap\n(OSMnx 2.0.7)"] --> P_NET["drive_network.graphml\n468 nodes, 884 edges"]
        FEMA["FEMA NFHL GeoPackage\n(802 Flood Features)"] --> P_HAZ["SFHA 100-Yr Zones\n(346 Polygons)"]
        USGS["USGS 3DEP (9 Tiles 1m DEM)\nUSGS FIM (0 Houston Sites)"] --> P_DEM["Elevation Grids\n(Track B Blocker)"]
        CENSUS["US Census TIGER 2024\n+ ACS 5-Yr B01003"] --> P_POP["548 Block Groups\n740,186 Population"]
    end

    subgraph DatabaseLayer ["2. Disposable Local Spatial Database (PostGIS 3.5.2 + pgRouting 3.7.3)"]
        P_NET --> T_ROADS["gis.road_nodes (468)\ngis.road_edges (884)"]
        P_HAZ --> T_FEMA["gis.fema_flood_zones (802)"]
        P_POP --> T_POP["gis.population_origins (548)"]
        
        T_ROADS & T_FEMA --> PROC_HAZ["compute_hazard_impacts.py\nST_Intersection (EPSG:26915)"]
        PROC_HAZ --> T_IMPACT["gis.scenario_edge_impacts\n(124 affected edges)"]
        
        T_ROADS & T_POP --> PROC_ACC["compute_population_accessibility.py\nVectorized pgr_dijkstra"]
        PROC_ACC --> T_ACC["gis.scenario_accessibility\n(1,096 records: 100% reconciled)"]
        
        FN_ROUTING["gis.route_edges()\ngis.route_nearest_facility()"]
    end

    subgraph APILayer ["3. FastAPI Backend Service (Python 3.12, Layered Architecture)"]
        CONFIG["core/config.py & database.py\n(statement_timeout = 8000ms)"]
        ROUTERS["Modular Routers:\n/health, /readiness, /study-areas,\n/facilities, /roads, /scenarios, /routes"]
        REPOS["repository/*_repo.py\nParameterized SQL, Bounding Box Guards"]
        SCHEMAS["schemas/*_schema.py\nTyped Pydantic Models, RFC 7946 GeoJSON"]
        MIDDLEWARE["core/logging.py\nX-Request-ID Tracking, Secret Masking"]
    end

    subgraph UILayer ["4. React 19 + MapLibre GL 5 Single Page Application"]
        MAP["MapLibre GL Map\nCarto Positron Tiles + OSM Attribution"]
        LAYERS["Layer Toggles:\nRoads, SFHA Closures, Facilities, Origins, Routes"]
        SIDEBAR["Analysis Sidebar:\nKPI Dashboard, 15/30/45m Toggles, Route Inspector"]
    end

    DatabaseLayer --> APILayer
    APILayer --> UILayer
```

---

## 2. Emergency Routing & Detour Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as Emergency Planner
    participant UI as React / MapLibre UI
    participant API as FastAPI Backend (/api/compare/routes)
    participant Repo as routing_repo.py
    participant DB as PostgreSQL / pgRouting

    User->>UI: Selects Origin Node (151461824) & Target "Hospital"
    UI->>API: GET /api/compare/routes?origin_node_id=151461824&facility_type=hospital&scenario_id=2
    API->>Repo: compare_routes(origin, hospital, scenario_id=2)
    
    rect rgb(240, 253, 244)
    Note over Repo,DB: 1. Compute Baseline Route (Normal Network)
    Repo->>DB: select * from gis.route_nearest_facility(151461824, 'hospital', NULL)
    DB-->>Repo: Baseline Path: 4 edges, travel_time = 72.4s, Saint Joseph Medical Center
    end

    rect rgb(254, 242, 242)
    Note over Repo,DB: 2. Compute Disrupted Route (Excluding 124 FEMA SFHA Closed Edges)
    Repo->>DB: select * from gis.route_nearest_facility(151461824, 'hospital', 2)
    DB-->>Repo: Disrupted Path: 7 edges, travel_time = 114.2s (Detour around flooded bayou)
    end

    Repo->>Repo: Calculate delay = +41.8s (+57.7%), status = "detoured"
    Repo->>Repo: Assemble continuous GeoJSON LineString coordinates
    Repo-->>API: CompareRouteResponse(status, delay, baseline, disrupted)
    API-->>UI: 200 OK JSON with GeoJSON route features
    UI-->>User: Renders Green Baseline line + Orange Dashed Detour line on map
```

---

## 3. Database Security & Concurrency Design

- **Row Level Security (RLS)**: Enabled across all 10 core tables in schema `gis`.
- **Security Invoker Functions**:
  - `gis.route_edges` and `gis.route_nearest_facility` are declared with `SECURITY INVOKER` and explicit `search_path = public, gis` to prevent search_path hijacking attacks while maintaining compatibility with pgRouting functions located in `public`.
- **Credential Masking**:
  - Regex sanitization in `core/errors.py` automatically strips connection usernames and passwords (`postgresql://user:***@host/db`) from log outputs and exception responses.
- **Query Timeouts**:
  - `statement_timeout = '8000ms'` enforced per connection to eliminate rogue blocking locks.
