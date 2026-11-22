-- Migration 002_local.sql — Local PostgreSQL version of schema improvements.
-- Apply after 001_local.sql in the local dev database.
-- For Supabase use 002_rls_and_schema_improvements.sql (extensions. prefix).

-- ============================================================
-- 1. Enable RLS on all nine core tables
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

-- ============================================================
-- 2. Add scenario_kind to flood_scenarios
-- ============================================================
alter table gis.flood_scenarios
  add column if not exists scenario_kind text not null default 'hazard_polygon'
    check (scenario_kind in ('baseline','hazard_polygon','depth_raster')),
  add column if not exists algorithm_version text,
  add column if not exists data_source_checksum text;

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
-- 6. FEMA hazard staging table
-- ============================================================
create table if not exists gis.fema_flood_zones (
  id bigint generated always as identity primary key,
  area_id bigint not null references gis.study_areas(id),
  fema_dfirm_id text,
  fld_zone text,
  sfha_tf text,
  zone_subtype text,
  source_feature_id text,
  geom geometry(MultiPolygon,4326),
  loaded_at timestamptz not null default now()
);
create index if not exists fema_flood_zones_geom_gix on gis.fema_flood_zones using gist(geom);
alter table gis.fema_flood_zones enable row level security;

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

-- ============================================================
-- 8. Add road topology metadata columns to road_edges
-- ============================================================
alter table gis.road_edges
  add column if not exists highway_class text,
  add column if not exists speed_kmh double precision,
  add column if not exists is_bridge boolean not null default false,
  add column if not exists is_tunnel boolean not null default false,
  add column if not exists layer_tag integer,
  add column if not exists osm_speed_source text;

-- ============================================================
-- 9. Function comment
-- ============================================================
comment on function gis.route_edges is
  'Returns Dijkstra shortest-path edges. Pass p_scenario=NULL for baseline.
   Closed edges (is_closed=true) are excluded (cost=-1).
   SECURITY INVOKER.';
