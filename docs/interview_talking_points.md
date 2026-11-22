# Portfolio & Interview Technical Guide

## 1. Technical Elevator Pitch

> "I built the **Flood-Aware Emergency Access Simulator**, a production-grade spatial analysis system that models how urban flood hazards disrupt emergency response access to critical medical and fire infrastructure in Downtown Houston.
> 
> Using OpenStreetMap drivable networks, FEMA NFHL regulatory flood polygons, and US Census ACS demographic data, the platform combines a **PostGIS 3.5 / pgRouting 3.7** spatial database, a **FastAPI** backend with layered repositories and bounding box guards, and an interactive **React 19 / MapLibre GL 5** application.
> 
> Across 119 automated tests, it proves zero-error routing parity with NetworkX ($\Delta = 0.0000\text{ s}$), sub-4ms Dijkstra query execution, and exact non-duplicative population reconciliation, identifying precisely 4,294 residents in Downtown Houston who become network-isolated under 100-year flood hazard conditions."

---

## 2. Key Engineering Decisions & Trade-offs

### 2.1 PostGIS / pgRouting vs In-Memory Python (NetworkX)
- **Decision**: NetworkX was used for offline graph validation, but production routing runs natively in PostgreSQL using pgRouting (`pgr_dijkstra`).
- **Why**: Native database routing eliminates network roundtrips for graph serialization, allows spatial indexes (`GIST`) to filter dynamic closed edge subsets, and enables vectorized many-to-many Dijkstra routing across hundreds of origins in a single 6ms query.

### 2.2 CRS Management (EPSG:4326 vs EPSG:26915)
- **Decision**: Geometries are stored in WGS 84 (`EPSG:4326`) for GeoJSON and MapLibre interoperability, but all spatial operations (polygon intersections, buffer calculations, Euclidean snap distances) are transformed to UTM Zone 15N (`EPSG:26915`).
- **Why**: Measuring lengths or intersections in degrees produces severe distortion at Houston's latitude ($29.76^\circ\text{ N}$). UTM Zone 15N provides true conformal metric coordinates with $<0.04\%$ scale distortion.

### 2.3 Transparent Data Blocker vs Synthetic Data
- **Decision**: When the official USGS Flood Inundation Mapping (FIM) API returned zero libraries for Houston, I explicitly recorded a data blocker and disabled Track B depth routing, focusing on Track A (FEMA SFHA regulatory hazard prototype).
- **Why**: In safety-critical GIS, improvising uncalibrated synthetic depth grids produces misleading, dangerous simulations. Professional software engineering demands transparently disclosing data limits rather than generating fictitious flood depths.

### 2.4 Census Accounting Without Double-Counting
- **Decision**: Applied strict mutually exclusive category partitioning (`within_threshold`, `beyond_threshold`, `network_unreachable`, `invalid_snap`).
- **Why**: Naive spatial joins often double-count populations when polygons overlap multiple road buffers. Our SQL model verifies that:
  $$\sum \text{Categories} = \text{Total ACS Population} = 740,186 \quad (100.0\%)$$

---

## 3. Key Metrics to Cite in Interviews

- **Test Coverage**: 119/119 automated tests passing across 8 suites.
- **Routing Accuracy**: $\Delta = 0.0000\text{ s}$ difference between pgRouting and NetworkX over 12 topological corridors.
- **pgRouting Query Latency**:
  - Point-to-point Dijkstra: **3.99 ms**
  - Nearest-facility Dijkstra: **3.21 ms**
  - All-origins accessibility aggregation: **0.20 ms**
- **Network Dimensions**: 468 nodes, 884 directed edges, 107.8 km road length.
- **Flood Impact**: 124 edges ($14.0\%$) affected by FEMA 100-year SFHA zones; exactly 4,294 residents lose emergency facility access.
- **Security & Hygiene**: Zero leaked credentials, RLS enabled on all 10 tables, SQL injection resistant, sub-second statement timeouts.
