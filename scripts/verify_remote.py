"""
scripts/verify_remote.py
Verify hosted Supabase database schema, tables, functions, and row counts.
"""
import os
import psycopg

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable must be set.")

conn = psycopg.connect(db_url)
cur = conn.cursor()

checks = [
    ("postgis extension", "select case when count(*)=1 then 'PASS' else 'FAIL' end from pg_extension where extname='postgis'"),
    ("pgrouting extension", "select case when count(*)=1 then 'PASS' else 'FAIL' end from pg_extension where extname='pgrouting'"),
    ("10 core tables present", """
        select case when count(*)=10 then 'PASS' else 'FAIL: ' || count(*) end 
        from information_schema.tables 
        where table_schema='gis' and table_name in (
            'study_areas','road_nodes','road_edges','facilities','population_origins',
            'flood_scenarios','scenario_edge_impacts','scenario_routes','scenario_accessibility','fema_flood_zones'
        )
    """),
    ("RLS enabled on all 10 tables", """
        select case when count(*)=10 then 'PASS' else 'FAIL: ' || count(*) end 
        from pg_tables 
        where schemaname='gis' and tablename in (
            'study_areas','road_nodes','road_edges','facilities','population_origins',
            'flood_scenarios','scenario_edge_impacts','scenario_routes','scenario_accessibility','fema_flood_zones'
        ) and rowsecurity=true
    """),
    ("spatial indexes (>=5)", "select case when count(*)>=5 then 'PASS (' || count(*) || ')' else 'FAIL: ' || count(*) end from pg_indexes where schemaname='gis' and indexname like '%gix%'"),
    ("gis.route_edges function", "select case when count(*)=1 then 'PASS' else 'FAIL' end from pg_proc where proname='route_edges' and pronamespace=(select oid from pg_namespace where nspname='gis')"),
    ("gis.route_to_destinations function", "select case when count(*)=1 then 'PASS' else 'FAIL' end from pg_proc where proname='route_to_destinations' and pronamespace=(select oid from pg_namespace where nspname='gis')"),
    ("gis.route_nearest_facility function", "select case when count(*)=1 then 'PASS' else 'FAIL' end from pg_proc where proname='route_nearest_facility' and pronamespace=(select oid from pg_namespace where nspname='gis')"),
    ("study_areas row count", "select count(*) from gis.study_areas"),
    ("road_nodes row count", "select count(*) from gis.road_nodes"),
    ("road_edges row count", "select count(*) from gis.road_edges"),
    ("facilities row count", "select count(*) from gis.facilities"),
    ("population_origins row count", "select count(*) from gis.population_origins"),
    ("flood_scenarios row count", "select count(*) from gis.flood_scenarios"),
    ("scenario_edge_impacts row count", "select count(*) from gis.scenario_edge_impacts"),
    ("scenario_accessibility row count", "select count(*) from gis.scenario_accessibility"),
    ("fema_flood_zones row count", "select count(*) from gis.fema_flood_zones")
]

all_pass = True
print("=" * 60)
print("SUPABASE POSTGRESQL VERIFICATION REPORT")
print("=" * 60)
for label, query in checks:
    cur.execute(query)
    val = cur.fetchone()[0]
    print(f"  {label:<35} : {val}")
    if "FAIL" in str(val):
        all_pass = False

conn.close()

if all_pass:
    print("=" * 60)
    print("ALL CHECKS PASSED SUCCESSFULLY")
    print("=" * 60)
else:
    print("=" * 60)
    print("SOME CHECKS FAILED")
    print("=" * 60)
    exit(1)
