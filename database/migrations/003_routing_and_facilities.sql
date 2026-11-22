-- Migration 003: Baseline emergency routing functions, one-to-many facility routing,
-- facility validation curation, and baseline scenario representation.
-- Apply after 002_local.sql in the local database.

-- ============================================================
-- 1. Fix search_path on gis.route_edges (SECURITY INVOKER)
-- ============================================================
create or replace function gis.route_edges(
  p_start bigint,
  p_end bigint,
  p_scenario bigint default null
)
returns table(
  seq integer,
  path_seq integer,
  node bigint,
  edge bigint,
  cost double precision,
  agg_cost double precision
)
language plpgsql
security invoker
set search_path = public, gis
as $fn$
begin
  return query
  select d.seq, d.path_seq, d.node, d.edge, d.cost, d.agg_cost
  from pgr_dijkstra(
    format(
      $q$select e.id, e.source, e.target,
        case when exists (
          select 1 from gis.scenario_edge_impacts i
          where i.edge_id = e.id and i.scenario_id = %s and i.is_closed
        ) then -1.0 else e.cost_s end as cost,
        case when exists (
          select 1 from gis.scenario_edge_impacts i
          where i.edge_id = e.id and i.scenario_id = %s and i.is_closed
        ) then -1.0 else e.reverse_cost_s end as reverse_cost
        from gis.road_edges e$q$,
      coalesce(p_scenario, -1),
      coalesce(p_scenario, -1)
    ),
    p_start,
    p_end,
    directed := true
  ) d;
end;
$fn$;
revoke execute on function gis.route_edges(bigint, bigint, bigint) from public;

-- ============================================================
-- 2. One-to-many routing function for destination sets
-- ============================================================
create or replace function gis.route_to_destinations(
  p_start bigint,
  p_targets bigint[],
  p_scenario bigint default null
)
returns table(
  seq integer,
  path_seq integer,
  start_vid bigint,
  end_vid bigint,
  node bigint,
  edge bigint,
  cost double precision,
  agg_cost double precision
)
language plpgsql
security invoker
set search_path = public, gis
as $fn$
begin
  return query
  select d.seq, d.path_seq, d.start_vid, d.end_vid, d.node, d.edge, d.cost, d.agg_cost
  from pgr_dijkstra(
    format(
      $q$select e.id, e.source, e.target,
        case when exists (
          select 1 from gis.scenario_edge_impacts i
          where i.edge_id = e.id and i.scenario_id = %s and i.is_closed
        ) then -1.0 else e.cost_s end as cost,
        case when exists (
          select 1 from gis.scenario_edge_impacts i
          where i.edge_id = e.id and i.scenario_id = %s and i.is_closed
        ) then -1.0 else e.reverse_cost_s end as reverse_cost
        from gis.road_edges e$q$,
      coalesce(p_scenario, -1),
      coalesce(p_scenario, -1)
    ),
    p_start,
    p_targets,
    directed := true
  ) d;
end;
$fn$;
revoke execute on function gis.route_to_destinations(bigint, bigint[], bigint) from public;

-- ============================================================
-- 3. Nearest reachable facility routing in a single query
-- ============================================================
create or replace function gis.route_nearest_facility(
  p_origin_node bigint,
  p_facility_type text default null,
  p_scenario bigint default null,
  p_area_id bigint default 1
)
returns table(
  facility_id bigint,
  facility_name text,
  facility_type text,
  facility_node_id bigint,
  total_travel_time_s double precision,
  edge_count integer,
  path_edges bigint[]
)
language plpgsql
security invoker
set search_path = public, gis
as $fn$
declare
  v_target_nodes bigint[];
begin
  -- Collect distinct road_node_ids of active, verified/candidate facilities
  select array_agg(distinct f.road_node_id)
  into v_target_nodes
  from gis.facilities f
  where f.area_id = p_area_id
    and f.is_active = true
    and f.validation_status in ('verified', 'candidate')
    and (p_facility_type is null or f.facility_type = p_facility_type)
    and f.road_node_id is not null;

  if v_target_nodes is null or array_length(v_target_nodes, 1) = 0 then
    return;
  end if;

  -- Same-node check: origin is already at a facility
  if p_origin_node = any(v_target_nodes) then
    return query
    select
      f.id, f.name, f.facility_type, f.road_node_id,
      0.0::double precision as total_travel_time_s,
      0 as edge_count,
      array[]::bigint[] as path_edges
    from gis.facilities f
    where f.road_node_id = p_origin_node
      and f.area_id = p_area_id
      and f.is_active = true
      and (p_facility_type is null or f.facility_type = p_facility_type)
    limit 1;
    return;
  end if;

  -- Run one-to-many Dijkstra and pick destination with lowest aggregate cost
  return query
  with paths as (
    select
      d.end_vid,
      d.edge,
      d.cost,
      d.agg_cost,
      d.path_seq
    from gis.route_to_destinations(p_origin_node, v_target_nodes, p_scenario) d
  ),
  dest_costs as (
    -- The destination vertex row in pgr_dijkstra has edge = -1 and agg_cost = total cost
    select
      p.end_vid,
      p.agg_cost as total_cost
    from paths p
    where p.edge = -1
    order by p.agg_cost asc
    limit 1
  ),
  chosen_path as (
    select
      p.edge,
      p.path_seq
    from paths p
    join dest_costs dc on dc.end_vid = p.end_vid
    where p.edge >= 0
    order by p.path_seq
  )
  select
    f.id as facility_id,
    f.name as facility_name,
    f.facility_type as facility_type,
    f.road_node_id as facility_node_id,
    dc.total_cost as total_travel_time_s,
    count(cp.edge)::integer as edge_count,
    array_agg(cp.edge order by cp.path_seq) as path_edges
  from dest_costs dc
  join gis.facilities f on f.road_node_id = dc.end_vid and f.area_id = p_area_id
  left join chosen_path cp on true
  where f.is_active = true
    and (p_facility_type is null or f.facility_type = p_facility_type)
  group by f.id, f.name, f.facility_type, f.road_node_id, dc.total_cost
  limit 1;
end;
$fn$;
revoke execute on function gis.route_nearest_facility(bigint, text, bigint, bigint) from public;

-- ============================================================
-- 4. Facility curation: verified, candidate, excluded
-- ============================================================
-- Acute care hospital: verified
update gis.facilities
set validation_status = 'verified',
    exclusion_reason = null,
    is_active = true,
    verified_at = now()
where name = 'Saint Joseph Medical Center';

-- Active municipal fire station: verified
update gis.facilities
set validation_status = 'verified',
    exclusion_reason = null,
    is_active = true,
    verified_at = now()
where name = 'Houston Fire Department Station 8';

-- Active municipal police headquarters: verified
update gis.facilities
set validation_status = 'verified',
    exclusion_reason = null,
    is_active = true,
    verified_at = now()
where name = 'Houston Police Department';

-- Specialist outpatient clinic: excluded from acute emergency routing
update gis.facilities
set validation_status = 'excluded',
    exclusion_reason = 'Specialist outpatient medical clinic; does not provide 24/7 acute trauma or emergency admission',
    is_active = false
where name = 'Houston Ear, Nose, Throat & Allergy Clinic';

-- Specialist outpatient center: excluded from acute emergency routing
update gis.facilities
set validation_status = 'excluded',
    exclusion_reason = 'Outpatient clinic; not a 24/7 emergency hospital',
    is_active = false
where name = 'Women''s Outpatient Center';

-- Administrative sheriff division: excluded from emergency dispatch/shelter
update gis.facilities
set validation_status = 'excluded',
    exclusion_reason = 'Administrative white-collar investigative division; does not house frontline emergency response or shelter',
    is_active = false
where name = 'Harris County Sheriff''s Office - Economic Crime';

-- General sheriff offices remain candidate for baseline review
update gis.facilities
set validation_status = 'candidate',
    exclusion_reason = null,
    is_active = true
where validation_status = 'candidate';

-- ============================================================
-- 5. Insert Baseline Flood Scenario (no edge impacts required)
-- ============================================================
insert into gis.flood_scenarios (
  area_id, name, description, scenario_kind, threshold_m, status
) values (
  1,
  'Baseline (Normal Conditions)',
  'Normal dry-weather operating conditions with all drivable roads open at baseline travel times.',
  'baseline',
  0.0,
  'ready'
) on conflict (area_id, name) do update
set scenario_kind = 'baseline',
    status = 'ready',
    threshold_m = 0.0;
