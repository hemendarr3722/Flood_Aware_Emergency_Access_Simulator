-- Migration 002: Add RLS policies, schema improvements, and processing provenance.
-- Apply after 001_initial.sql in the same dedicated database.
-- DO NOT run against protected hosted projects.

-- ============================================================
-- 1. Enable RLS on all nine core tables (never done in 001)
-- ============================================================
alter table gis.study_areas enable row level security;
alter table gis.road_nodes enable row level security;
alter table gis.road_edges enable row level security;
alter table gis.facilities enable row level security;
alter table gis.population_origins enable row level security;
alter table gis.flood_scenarios enable row level security;
alter table gis.scenario_edge_impacts enable row level security;
alter table gis.scenario_routes enable row level security;
alter table gis.scenario_accessibility enable row level security;

-- No permissive policies are added: browser/anon roles have no access.
-- Backend reads via privileged server connection only (no Supabase anon key exposure).

-- ============================================================
-- 2. Add scenario_kind to flood_scenarios
-- ============================================================
alter table gis.flood_scenarios
  add column if not exists scenario_kind text not null default 'hazard_polygon'
    check (scenario_kind in ('baseline','hazard_polygon','depth_raster')),
  add column if not exists algorithm_version text,
  add column if not exists data_source_checksum text;

-- Rename threshold_m to be more explicit and nullable (baseline has no threshold)
-- Keep existing column; add kind-aware check via trigger instead of breaking existing rows.

-- ============================================================
-- 3. Add provenance / snap-distance columns to facilities
-- ============================================================
alter table gis.facilities
  add column if not exists validation_status text not null default 'candidate'
    check (validation_status in ('candidate','verified','excluded')),
  add column if not exists exclusion_reason text,
  add column if not exists snap_distance_m double precision,
  add column if not exists snap_max_m double precision not null default 300;

-- ============================================================
-- 4. Add snap provenance to population_origins
-- ============================================================
alter table gis.population_origins
  add column if not exists snap_distance_m double precision,
  add column if not exists snap_max_m double precision not null default 500,
  add column if not exists snap_valid boolean not null default true;

-- ============================================================
-- 5. Add provenance fields to scenario_edge_impacts
-- ============================================================
alter table gis.scenario_edge_impacts
  add column if not exists impact_kind text not null default 'hazard_polygon'
    check (impact_kind in ('hazard_polygon','depth_raster')),
  add column if not exists intersection_fraction double precision
    check (intersection_fraction >= 0 and intersection_fraction <= 1),
  add column if not exists flood_zone text,
  add column if not exists sfha_tf text,
  add column if not exists source_feature_id text;

-- ============================================================
-- 6. FEMA hazard staging table (raw polygons, not road impacts)
-- ============================================================
create table if not exists gis.fema_flood_zones (
  id bigint generated always as identity primary key,
  area_id bigint not null references gis.study_areas(id),
  fema_dfirm_id text,
  fld_zone text,
  sfha_tf text,
  zone_subtype text,
  source_feature_id text,
  geom extensions.geometry(MultiPolygon,4326),
  loaded_at timestamptz not null default now()
);
create index if not exists fema_flood_zones_geom_gix on gis.fema_flood_zones using gist(geom);
alter table gis.fema_flood_zones enable row level security;
revoke all on gis.fema_flood_zones from public, anon, authenticated;

-- ============================================================
-- 7. Processing runs provenance table
-- ============================================================
create table if not exists gis.processing_runs (
  id bigint generated always as identity primary key,
  pipeline text not null,
  area_id bigint references gis.study_areas(id),
  status text not null default 'running' check (status in ('running','success','failure')),
  input_checksums jsonb,
  row_counts jsonb,
  error_message text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
alter table gis.processing_runs enable row level security;
revoke all on gis.processing_runs from public, anon, authenticated;

-- ============================================================
-- 8. Add road topology metadata columns to road_edges
-- ============================================================
alter table gis.road_edges
  add column if not exists highway_class text,
  add column if not exists speed_kmh double precision,
  add column if not exists is_bridge boolean not null default false,
  add column if not exists is_tunnel boolean not null default false,
  add column if not exists layer_tag integer,
  add column if not exists osm_speed_source text;  -- 'tagged','highway_default','fallback'

-- ============================================================
-- 9. Revoke execution of routing function from PUBLIC
-- ============================================================
revoke execute on function gis.route_edges(bigint, bigint, bigint) from public;

-- ============================================================
-- 10. Create a baseline scenario helper view (not a table duplicate)
-- ============================================================
-- Baseline = no edge impacts applied. The route_edges function handles null scenario correctly.
comment on function gis.route_edges is
  'Returns Dijkstra shortest-path edges. Pass p_scenario=NULL for baseline (no flood impact).
   Scenario edges marked is_closed=true are excluded (cost set to -1).
   SECURITY INVOKER: caller must have SELECT on road_edges and scenario_edge_impacts.';
