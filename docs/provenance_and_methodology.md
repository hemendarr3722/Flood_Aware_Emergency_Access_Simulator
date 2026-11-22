# Data Provenance & Modeling Methodology

## 1. Upstream Data Provenance

| Dataset | Custodian / Source | Canonical Extent | Local Artifact / Hash | Processing Method |
| --- | --- | --- | --- | --- |
| **Drive Network** | OpenStreetMap / Overpass | Downtown Houston Pilot `[-95.385, 29.740, -95.345, 29.775]` | `data/raw/osm_pilot_extract.json` / `drive_network.graphml` | OSMnx 2.0.7 `graph_from_polygon` filtered to drivable edges with posted speeds and standard fallbacks. |
| **Flood Hazard** | FEMA National Flood Hazard Layer (NFHL) | Harris County, TX (FIPS 48201) | `data/raw/fema_nfhl_pilot.gpkg` (802 features) | Repaired via `ST_Buffer(geom, 0)`; filtered to Special Flood Hazard Area (SFHA, 1% annual chance) zones A, AE, AO. |
| **DEM Elevation** | USGS 3D Elevation Program (3DEP) | Downtown Houston Pilot (9 tiles) | `data/raw/usgs_3dep_dem.tif` (1m resolution, EPSG:26915) | Validated against USGS National Map hashes. Elevation represents bare-earth surface, NOT flood depth. |
| **Flood Inundation Depth** | USGS Flood Inundation Mapping (FIM) | Greater Houston Extent | *Blocked by data* | Official USGS FIM public catalog API returned 0 matching libraries. Documented as Track B data blocker. |
| **Census Geography** | US Census Bureau TIGER/Line | 2024 Texas Block Groups | `tl_2024_48_bg.zip` (18,638 BG geometries) | Clipped to pilot bounding box; validated 12-char GEOIDs (`48201...`). |
| **Census Population** | US Census Bureau 2024 ACS 5-Year | Table B01003 (Total Population) | `data/raw/census_acs_b01003.csv` | Harris County block groups extracted; validated non-negative values; reconciled with TIGER geometry. |

---

## 2. Mathematical Methodology & Modeling Rules

### 2.1 Road Travel Time Formulation
Travel time cost $t_e$ (seconds) for road edge $e$ with length $L_e$ (metres) and speed $v_e$ (km/h) is formulated as:
$$t_e = \frac{L_e}{v_e \times \frac{1000}{3600}}$$

For one-way roads, the reverse cost $t_{e,\text{rev}}$ is set to $-1.0$, rendering backward traversal impassable in Dijkstra path searches.

### 2.2 FEMA SFHA Hazard-Polygon Impact Model (Track A)
For each road edge $e \in E$, the intersection with FEMA SFHA polygon geometry $P_{\text{SFHA}} = \bigcup_{p \in \text{SFHA}} p$ is evaluated in projected coordinates (EPSG:26915):
$$L_{\text{intersect}} = \text{Length}\left(e \cap P_{\text{SFHA}}\right)$$
$$\text{Fraction}(e) = \frac{L_{\text{intersect}}}{L_e}$$

- **Edge Exclusion Rule**: Any drivable edge with $L_{\text{intersect}} > 0$ is marked as `is_closed = true` in Scenario 2 (`scenario_kind = 'hazard_polygon'`).
- In this pilot network of 884 directed edges, exactly **124 edges ($14.0\%$, $15,119.3\text{ m}$)** intersect SFHA zones and are excluded from emergency routes.
- **Labeling Mandate**: Edges are strictly documented as *"modeled potentially affected roads"* under regulatory hazard zones. They are **never** described as *"inundated"* or *"depth-based closures"*.

### 2.3 Representative Origins & Network Snapping
- Naive polygon centroids can fall outside concave boundaries (e.g., U-shaped block groups bordering bayous). Representative origin coordinates are generated using `shapely.point_on_surface(P)`, guaranteeing that the representative coordinate lies strictly inside the block-group polygon.
- Projected Euclidean distance $d(P, v)$ to the nearest drivable network node $v \in V$ is calculated in EPSG:26915.
- Origins with $d(P, v) \le 500.0\text{ m}$ are successfully snapped to the graph. Origins with $d(P, v) > 500.0\text{ m}$ are classified as `invalid_snap` and documented as outside the pilot network buffer.

### 2.4 Multi-Threshold Accessibility Accounting (15, 30, 45 min)
Let $T = \{900\text{ s}, 1800\text{ s}, 2700\text{ s}\}$ be the threshold set. For scenario $S$ and origin $o$ with population $N_o$ and minimum facility travel time $t_o(S)$:
$$\text{Status}(o, S) = \begin{cases}
\text{within\_threshold} & \text{if } o \text{ reachable and } t_o(S) \le \tau \\
\text{beyond\_threshold} & \text{if } o \text{ reachable and } t_o(S) > \tau \\
\text{network\_unreachable} & \text{if } o \text{ has valid snap but no path to active facility} \\
\text{invalid\_snap} & \text{if } o \text{ has snap distance } > 500\text{ m}
\end{cases}$$

**Non-Duplicative Invariant**:
Every origin belongs to exactly one category per threshold $\tau$. The aggregate population sums identically to the total input Census population:
$$\sum_{o \in \text{Within}} N_o + \sum_{o \in \text{Beyond}} N_o + \sum_{o \in \text{Unreachable}} N_o + \sum_{o \in \text{Invalid}} N_o = \sum_{o \in O} N_o = 740,186$$

---

## 3. Depth-Raster Track B Governance

1. **Discovery Failure**: The official USGS FIM public catalog API (`https://fim.wim.usgs.gov/fim/rest/services/FIM/FIMMapper/MapServer/...`) was queried with coordinates covering Greater Houston. Zero libraries were returned.
2. **Blocker Enforcement**: Rather than improvising synthetic or uncalibrated depth values, Track B is disabled with an explicit data blocker recorded in `IMPLEMENTATION_STATUS.md`.
3. **Preparedness Tests**: Unit test fixtures in `pipelines/tests/test_depth_invariants.py` verify that if authentic depth grids become available in the future:
   - Nodata values (`-9999.0`, `-32767.0`, `NaN`) are never coerced to zero depth.
   - Metric conversions ($1\text{ m} = 3.28084\text{ ft}$) are strictly bidirectional.
   - Depth hazard classification is monotonic ($0 < 0.15\text{ m} < 0.30\text{ m} < 0.60\text{ m}$).
