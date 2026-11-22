-- database/verify.sql
-- Run against the dedicated local database after migrations to confirm:
--   extensions, 10 core tables, indexes, RLS, routing function, and row counts.
-- Usage: psql "$DATABASE_URL" -f database/verify.sql
-- Expected: all checks print PASS. Any FAIL line indicates a problem.

\set ON_ERROR_STOP on

-- ── 1. Extensions ─────────────────────────────────────────────────────────────
select case when count(*)=1 then 'PASS: postgis extension' else 'FAIL: postgis missing' end
  from pg_extension where extname='postgis';

select case when count(*)=1 then 'PASS: pgrouting extension' else 'FAIL: pgrouting missing' end
  from pg_extension where extname='pgrouting';

-- ── 2. Core tables exist ───────────────────────────────────────────────────────
select case when count(*)=10 then 'PASS: 10 core tables present'
            else 'FAIL: expected 10 tables, found '||count(*) end
from information_schema.tables
where table_schema='gis'
  and table_name in (
    'study_areas','road_nodes','road_edges','facilities','population_origins',
    'flood_scenarios','scenario_edge_impacts','scenario_routes',
    'scenario_accessibility','fema_flood_zones'
  );

-- ── 3. RLS enabled on every table ─────────────────────────────────────────────
select case when count(*)=10 then 'PASS: RLS enabled on all 10 tables'
            else 'FAIL: RLS not enabled on '||(10-count(*))||' table(s): '||
              string_agg(tablename,' ') end
from pg_tables
where schemaname='gis'
  and tablename in (
    'study_areas','road_nodes','road_edges','facilities','population_origins',
    'flood_scenarios','scenario_edge_impacts','scenario_routes',
    'scenario_accessibility','fema_flood_zones'
  )
  and rowsecurity=true;

-- ── 4. Spatial indexes ─────────────────────────────────────────────────────────
select case when count(*)>=5 then 'PASS: spatial indexes present ('||count(*)||')'
            else 'FAIL: expected >=5 spatial indexes, found '||count(*) end
from pg_indexes
where schemaname='gis'
  and indexname like '%gix%';

-- ── 5. Routing function present ───────────────────────────────────────────────
select case when count(*)=1 then 'PASS: gis.route_edges function exists'
            else 'FAIL: gis.route_edges missing' end
from pg_proc
where proname='route_edges'
  and pronamespace=(select oid from pg_namespace where nspname='gis');

-- ── 6. Routing function is SECURITY INVOKER ───────────────────────────────────
select case when prosecdef=false then 'PASS: route_edges is SECURITY INVOKER'
            else 'FAIL: route_edges is SECURITY DEFINER' end
from pg_proc
where proname='route_edges'
  and pronamespace=(select oid from pg_namespace where nspname='gis');

-- ── 7. anon/authenticated cannot execute routing function ────────────────────
-- (Only verifiable if roles exist. Skip gracefully if roles are absent.)
select case
  when not exists (select 1 from pg_roles where rolname in ('anon','authenticated'))
  then 'INFO: anon/authenticated roles not present (local dev) — skipping privilege check'
  when not exists (
    select 1 from information_schema.routine_privileges
    where specific_schema='gis' and routine_name='route_edges'
      and grantee in ('anon','authenticated') and privilege_type='EXECUTE'
  )
  then 'PASS: anon/authenticated cannot execute route_edges'
  else 'FAIL: anon or authenticated can execute route_edges'
end;

-- ── 8. No permissive RLS policies grant public access ────────────────────────
select case when count(*)=0 then 'PASS: no permissive policies for public/anon/authenticated'
            else 'FAIL: '||count(*)||' permissive policies expose data to unintended roles' end
from pg_policies
where schemaname='gis'
  and cmd in ('SELECT','ALL')
  and permissive='PERMISSIVE'
  and (roles @> array['public'::name] or roles @> array['anon'::name] or roles @> array['authenticated'::name]);

-- ── 9. road_edges columns ─────────────────────────────────────────────────────
select case when count(*)>=8 then 'PASS: road_edges has routing columns'
            else 'FAIL: road_edges missing columns' end
from information_schema.columns
where table_schema='gis' and table_name='road_edges'
  and column_name in ('source','target','length_m','cost_s','reverse_cost_s','highway_class','speed_kmh','is_bridge');

-- ── 10. facilities has validation_status ──────────────────────────────────────
select case when count(*)=1 then 'PASS: facilities.validation_status present'
            else 'FAIL: facilities.validation_status missing' end
from information_schema.columns
where table_schema='gis' and table_name='facilities' and column_name='validation_status';

-- ── 11. flood_scenarios has scenario_kind ────────────────────────────────────
select case when count(*)=1 then 'PASS: flood_scenarios.scenario_kind present'
            else 'FAIL: flood_scenarios.scenario_kind missing' end
from information_schema.columns
where table_schema='gis' and table_name='flood_scenarios' and column_name='scenario_kind';

-- ── 12. processing_runs table present ─────────────────────────────────────────
select case when count(*)=1 then 'PASS: gis.processing_runs table present'
            else 'FAIL: gis.processing_runs missing' end
from information_schema.tables
where table_schema='gis' and table_name='processing_runs';

-- ── 13. Row counts after ingestion (requires data to be loaded first) ─────────
-- These checks are advisory; they show 0 on a fresh empty DB, which is expected.
select 'INFO: study_areas rows='||count(*) from gis.study_areas;
select 'INFO: road_nodes rows='||count(*) from gis.road_nodes;
select 'INFO: road_edges rows='||count(*) from gis.road_edges;
select 'INFO: facilities rows='||count(*) from gis.facilities;
select 'INFO: fema_flood_zones rows='||count(*) from gis.fema_flood_zones;
select 'INFO: population_origins rows='||count(*) from gis.population_origins;
