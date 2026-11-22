-- Run only in a NEW dedicated Supabase project, never in existing projects.
create schema if not exists gis;
create extension if not exists postgis with schema extensions;
create extension if not exists pgrouting with schema extensions cascade;

create table gis.study_areas (
 id bigint generated always as identity primary key,
 name text unique not null,
 boundary extensions.geometry(MultiPolygon,4326),
 created_at timestamptz not null default now()
);
create table gis.road_nodes (
 id bigint primary key,
 area_id bigint not null references gis.study_areas(id),
 geom extensions.geometry(Point,4326) not null
);
create index road_nodes_geom_gix on gis.road_nodes using gist(geom);
create table gis.road_edges (
 id bigint generated always as identity primary key,
 area_id bigint not null references gis.study_areas(id),
 osm_way_id text,
 source bigint not null references gis.road_nodes(id),
 target bigint not null references gis.road_nodes(id),
 length_m double precision not null check (length_m > 0),
 cost_s double precision not null check (cost_s > 0),
 reverse_cost_s double precision not null default -1,
 geom extensions.geometry(LineString,4326) not null,
 constraint reverse_cost_valid check (reverse_cost_s = -1 or reverse_cost_s > 0)
);
create index road_edges_geom_gix on gis.road_edges using gist(geom);
create index road_edges_source_idx on gis.road_edges(source);
create index road_edges_target_idx on gis.road_edges(target);
create table gis.facilities (
 id bigint generated always as identity primary key,
 area_id bigint not null references gis.study_areas(id),
 osm_id text,
 name text not null,
 facility_type text not null check (facility_type in ('hospital','shelter','fire_station')),
 is_active boolean not null default true,
 geom extensions.geometry(Point,4326) not null,
 road_node_id bigint references gis.road_nodes(id),
 source text not null default 'OSM',
 verified_at timestamptz
);
create index facilities_geom_gix on gis.facilities using gist(geom);
create table gis.population_origins (
 id bigint generated always as identity primary key,
 area_id bigint not null references gis.study_areas(id),
 geoid text not null,
 population integer not null check (population >= 0),
 geom extensions.geometry(Point,4326) not null,
 road_node_id bigint references gis.road_nodes(id),
 population_year integer,
 unique (area_id,geoid)
);
create index population_origins_geom_gix on gis.population_origins using gist(geom);
create table gis.flood_scenarios (
 id bigint generated always as identity primary key,
 area_id bigint not null references gis.study_areas(id),
 name text not null,
 description text,
 raster_uri text,
 raster_source text,
 threshold_m double precision not null check (threshold_m >= 0),
 status text not null default 'draft' check (status in ('draft','ready')),
 created_at timestamptz not null default now(),
 unique(area_id,name)
);
create table gis.scenario_edge_impacts (
 scenario_id bigint not null references gis.flood_scenarios(id) on delete cascade,
 edge_id bigint not null references gis.road_edges(id) on delete cascade,
 depth_m double precision check (depth_m >= 0),
 is_closed boolean not null,
 primary key(scenario_id,edge_id)
);
create index scenario_edge_closed_idx on gis.scenario_edge_impacts(scenario_id,edge_id) where is_closed;
create table gis.scenario_routes (
 id bigint generated always as identity primary key,
 scenario_id bigint not null references gis.flood_scenarios(id) on delete cascade,
 origin_node_id bigint not null references gis.road_nodes(id),
 facility_id bigint references gis.facilities(id),
 travel_time_s double precision,
 route_geom extensions.geometry(MultiLineString,4326),
 unique(scenario_id,origin_node_id,facility_id)
);
create table gis.scenario_accessibility (
 scenario_id bigint not null references gis.flood_scenarios(id) on delete cascade,
 origin_id bigint not null references gis.population_origins(id) on delete cascade,
 facility_id bigint references gis.facilities(id),
 travel_time_s double precision,
 reachable boolean not null,
 population integer not null check(population >= 0),
 primary key(scenario_id,origin_id)
);
-- All application tables are private: frontend has NO direct database access.
revoke all on schema gis from public, anon, authenticated;
revoke all on all tables in schema gis from public, anon, authenticated;
-- Routing functions use static, server-owned edges SQL. Scenarios never modify road geometry.
create or replace function gis.route_edges(p_start bigint, p_end bigint, p_scenario bigint default null)
returns table(seq integer, path_seq integer, node bigint, edge bigint, cost double precision, agg_cost double precision)
language plpgsql security invoker set search_path = '' as $fn$
begin
 return query select d.seq,d.path_seq,d.node,d.edge,d.cost,d.agg_cost
 from extensions.pgr_dijkstra(
   format($q$select e.id, e.source, e.target,
     case when exists (select 1 from gis.scenario_edge_impacts i where i.edge_id=e.id and i.scenario_id=%s and i.is_closed) then -1.0 else e.cost_s end as cost,
     case when exists (select 1 from gis.scenario_edge_impacts i where i.edge_id=e.id and i.scenario_id=%s and i.is_closed) then -1.0 else e.reverse_cost_s end as reverse_cost
     from gis.road_edges e$q$, coalesce(p_scenario,-1), coalesce(p_scenario,-1)),
   p_start, p_end, directed:=true) d;
end; $fn$;
