-- database/verify_local.sql
-- Local PostgreSQL version of verify.sql (no extensions. schema prefix).
-- Usage: psql "$DATABASE_URL" -f database/verify_local.sql

-- ── 1. Extensions ─────────────────────────────────────────────────────────────
select case when count(*)=1 then 'PASS: postgis extension' else 'FAIL: postgis missing' end
  from pg_extension where extname='postgis';

select case when count(*)=1 then 'PASS: pgrouting extension' else 'FAIL: pgrouting missing' end
  from pg_extension where extname='pgrouting';

-- ── 2. Core tables ────────────────────────────────────────────────────────────
select case when count(*)=10 then 'PASS: 10 core tables present'
            else 'FAIL: expected 10 tables, found '||count(*) end
from information_schema.tables
where table_schema='gis'
  and table_name in (
    'study_areas','road_nodes','road_edges','facilities','population_origins',
    'flood_scenarios','scenario_edge_impacts','scenario_routes',
    'scenario_accessibility','fema_flood_zones'
  );

-- ── 3. RLS enabled ────────────────────────────────────────────────────────────
select case when count(*)=10 then 'PASS: RLS enabled on all 10 tables'
            else 'FAIL: RLS not enabled on '||(10-count(*))||' table(s)' end
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
where schemaname='gis' and indexname like '%gix%';

-- ── 5. Routing function present ───────────────────────────────────────────────
select case when count(*)=1 then 'PASS: gis.route_edges function exists'
            else 'FAIL: gis.route_edges missing' end
from pg_proc
where proname='route_edges'
  and pronamespace=(select oid from pg_namespace where nspname='gis');

-- ── 6. SECURITY INVOKER ───────────────────────────────────────────────────────
select case when prosecdef=false then 'PASS: route_edges is SECURITY INVOKER'
            else 'FAIL: route_edges is SECURITY DEFINER' end
from pg_proc
where proname='route_edges'
  and pronamespace=(select oid from pg_namespace where nspname='gis');

-- ── 7. scenario_kind column ───────────────────────────────────────────────────
select case when count(*)=1 then 'PASS: flood_scenarios.scenario_kind present'
            else 'FAIL: flood_scenarios.scenario_kind missing' end
from information_schema.columns
where table_schema='gis' and table_name='flood_scenarios' and column_name='scenario_kind';

-- ── 8. facilities.validation_status ──────────────────────────────────────────
select case when count(*)=1 then 'PASS: facilities.validation_status present'
            else 'FAIL: facilities.validation_status missing' end
from information_schema.columns
where table_schema='gis' and table_name='facilities' and column_name='validation_status';

-- ── 9. processing_runs ────────────────────────────────────────────────────────
select case when count(*)=1 then 'PASS: gis.processing_runs present'
            else 'FAIL: gis.processing_runs missing' end
from information_schema.tables
where table_schema='gis' and table_name='processing_runs';

-- ── 10. PostGIS + pgRouting versions ─────────────────────────────────────────
select 'INFO: PostGIS version=' || postgis_full_version();
select 'INFO: pgRouting version=' || pgr_version();

-- ── 11. Row counts after ingestion ───────────────────────────────────────────
select 'INFO: study_areas rows='||count(*) from gis.study_areas;
select 'INFO: road_nodes rows='||count(*) from gis.road_nodes;
select 'INFO: road_edges rows='||count(*) from gis.road_edges;
select 'INFO: facilities rows='||count(*) from gis.facilities;
select 'INFO: fema_flood_zones rows='||count(*) from gis.fema_flood_zones;
select 'INFO: population_origins rows='||count(*) from gis.population_origins;
select 'INFO: processing_runs rows='||count(*) from gis.processing_runs;
