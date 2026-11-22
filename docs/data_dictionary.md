# Data Dictionary & Schema Specification

All tables reside in the private `gis` schema with Row Level Security (RLS) enabled. Coordinates are stored in `EPSG:4326` (WGS 84 geographic latitude/longitude) for external interoperability and projected dynamically or cached in `EPSG:26915` (UTM Zone 15N, metres) for accurate Euclidean and metric operations.

---

## 1. Core Road Network & Routing

### `gis.road_nodes`
Represents graph vertices derived from OpenStreetMap intersections and dead-ends.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. Matches OSM node ID where available. |
| `area_id` | `bigint` | No | Foreign key referencing `gis.study_areas(id)`. |
| `geom` | `geometry(Point, 4326)` | No | Node geographic location. Indexed with SP-GiST / GiST. |

### `gis.road_edges`
Directed graph edges for Dijkstra shortest path routing.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. Unique edge identifier. |
| `area_id` | `bigint` | No | Foreign key referencing `gis.study_areas(id)`. |
| `source` | `bigint` | No | Starting vertex ID referencing `gis.road_nodes(id)`. |
| `target` | `bigint` | No | Ending vertex ID referencing `gis.road_nodes(id)`. |
| `length_m` | `double precision` | No | Edge length in projected metres ($>0$). |
| `speed_kmh` | `double precision` | No | Posted or default speed limit in km/h ($>0$). |
| `cost_s` | `double precision` | No | Forward traversal travel time: $t = \frac{\text{length\_m}}{\text{speed\_kmh} \times (1000/3600)}$. |
| `reverse_cost_s` | `double precision` | No | Reverse cost: equal to `cost_s` for two-way roads; `-1.0` for one-way roads. |
| `highway_class` | `text` | Yes | OSM highway tag (e.g., `motorway`, `primary`, `residential`). |
| `geom` | `geometry(LineString, 4326)` | No | Edge geometry in WGS 84. Spatial index present. |

---

## 2. Emergency Facilities

### `gis.facilities`
Emergency response destinations curated into verified, candidate, and excluded tiers.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. |
| `area_id` | `bigint` | No | Foreign key referencing `gis.study_areas(id)`. |
| `name` | `text` | No | Name of facility (e.g. `Saint Joseph Medical Center`). |
| `facility_type` | `text` | No | Enum check: `'hospital'`, `'shelter'`, `'fire_station'`. |
| `is_active` | `boolean` | No | Operational status flag. |
| `validation_status` | `text` | No | Curation tier: `'verified'`, `'candidate'`, `'excluded'`. |
| `exclusion_reason` | `text` | Yes | Documented rationale when status is `'excluded'`. |
| `snap_distance_m` | `double precision` | Yes | Projected Euclidean distance to nearest road network node. |
| `road_node_id` | `bigint` | Yes | Nearest snapped node ID in `gis.road_nodes(id)`. |
| `geom` | `geometry(Point, 4326)` | No | Facility location in WGS 84. |

---

## 3. Flood Hazards & Scenarios

### `gis.fema_flood_zones`
Staging table for regulatory flood hazard polygons imported from FEMA NFHL.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. |
| `fld_ar_id` | `text` | Yes | Unique FEMA feature ID. |
| `fld_zone` | `text` | No | Regulatory flood zone: `A`, `AE`, `AO`, `VE`, `X`. |
| `sfha_tf` | `text` | No | Special Flood Hazard Area flag (`'T'` for 100-year, `'F'` for 500-year/minimal). |
| `geom` | `geometry(MultiPolygon, 4326)` | No | Validated, repaired multipolygon (`ST_Buffer(geom, 0)`). |

### `gis.flood_scenarios`
Registered scenario definitions (baseline normal vs flood hazard models).
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. (1 = Baseline, 2 = FEMA SFHA Prototype). |
| `area_id` | `bigint` | No | Foreign key referencing `gis.study_areas(id)`. |
| `name` | `text` | No | Scenario display name. |
| `scenario_kind` | `text` | No | Enum check: `'baseline'`, `'hazard_polygon'`, `'depth_grid'`. |
| `threshold_m` | `double precision` | Yes | Inundation depth threshold (null for polygon tracks). |
| `algorithm_version` | `text` | No | Algorithm identifier (e.g. `fema_sfha_intersection_v1`). |
| `status` | `text` | No | Execution state: `'draft'`, `'running'`, `'ready'`, `'failed'`. |

### `gis.scenario_edge_impacts`
Precomputed edge closures and hazard intersections per scenario.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `scenario_id` | `bigint` | No | Composite PK part. References `gis.flood_scenarios(id)`. |
| `edge_id` | `bigint` | No | Composite PK part. References `gis.road_edges(id)`. |
| `is_closed` | `boolean` | No | If `true`, edge is excluded from routing in this scenario. |
| `impact_kind` | `text` | No | `'polygon_intersection'` (Track A) or `'depth_threshold'` (Track B). |
| `flood_zone` | `text` | Yes | Associated FEMA flood zone code. |
| `sfha_tf` | `text` | Yes | FEMA SFHA flag (`'T'`). |
| `intersection_fraction`| `double precision` | Yes | Fraction of edge length intersecting hazard polygon ($0.0 - 1.0$). |

---

## 4. Population Origins & Accessibility

### `gis.population_origins`
Census block-group representative origins with ACS population.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `bigint` | No | Primary key. |
| `area_id` | `bigint` | No | References `gis.study_areas(id)`. |
| `geoid` | `text` | No | 12-character Census GEOID (State FIPS 48 + County 201 + Tract + Block Group). |
| `population` | `integer` | No | ACS 5-year total population ($B01003\_001E \ge 0$). |
| `snap_distance_m` | `double precision` | Yes | Distance to nearest road network node in metres. |
| `road_node_id` | `bigint` | Yes | Snapped road network vertex ID ($NULL$ if $>500\text{ m}$). |
| `geom` | `geometry(Point, 4326)` | No | Representative coordinates (`shapely.point_on_surface`). |

### `gis.scenario_accessibility`
Precomputed one-to-one origin accessibility metrics per scenario.
| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `scenario_id` | `bigint` | No | References `gis.flood_scenarios(id)`. |
| `origin_id` | `bigint` | No | References `gis.population_origins(id)`. |
| `facility_id` | `bigint` | Yes | Nearest reachable facility ID ($NULL$ if unreachable). |
| `travel_time_s` | `double precision` | Yes | Minimum travel time in seconds ($NULL$ if unreachable, never $0$). |
| `reachable` | `boolean` | No | `true` if viable path exists to an active facility. |
| `status_category` | `text` | No | `'within_threshold'`, `'beyond_threshold'`, `'network_unreachable'`, `'invalid_snap'`. |
| `threshold_15min` | `boolean` | No | `true` if `reachable` and `travel_time_s <= 900.0`. |
| `threshold_30min` | `boolean` | No | `true` if `reachable` and `travel_time_s <= 1800.0`. |
| `threshold_45min` | `boolean` | No | `true` if `reachable` and `travel_time_s <= 2700.0`. |
| `population` | `integer` | No | Copied from origin row to guarantee 100% exact reconciliation. |
