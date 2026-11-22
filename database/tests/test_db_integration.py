"""
database/tests/test_db_integration.py — Integration tests requiring a live PostGIS database.

Skip all tests unless DATABASE_URL env var is set.
Run with: pytest database/tests/test_db_integration.py -v
"""
import json
import os
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live database integration tests",
)


@pytest.fixture(scope="session")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(DATABASE_URL, row_factory=dict_row) as c:
        yield c


@skip_no_db
class TestExtensions:
    def test_postgis_present(self, conn):
        row = conn.execute("select count(*) cnt from pg_extension where extname='postgis'").fetchone()
        assert row["cnt"] == 1, "PostGIS extension not installed"

    def test_pgrouting_present(self, conn):
        row = conn.execute("select count(*) cnt from pg_extension where extname='pgrouting'").fetchone()
        assert row["cnt"] == 1, "pgRouting extension not installed"


@skip_no_db
class TestSchema:
    def test_core_tables_exist(self, conn):
        expected = {
            "study_areas", "road_nodes", "road_edges", "facilities",
            "population_origins", "flood_scenarios", "scenario_edge_impacts",
            "scenario_routes", "scenario_accessibility", "fema_flood_zones",
        }
        rows = conn.execute(
            "select table_name from information_schema.tables where table_schema='gis'"
        ).fetchall()
        found = {r["table_name"] for r in rows}
        missing = expected - found
        assert not missing, f"Missing tables: {missing}"

    def test_rls_enabled(self, conn):
        rows = conn.execute(
            "select tablename, rowsecurity from pg_tables where schemaname='gis'"
        ).fetchall()
        not_rls = [r["tablename"] for r in rows if not r["rowsecurity"]]
        assert not not_rls, f"RLS not enabled on: {not_rls}"

    def test_scenario_kind_column(self, conn):
        row = conn.execute(
            "select count(*) cnt from information_schema.columns "
            "where table_schema='gis' and table_name='flood_scenarios' and column_name='scenario_kind'"
        ).fetchone()
        assert row["cnt"] == 1, "flood_scenarios.scenario_kind column missing"

    def test_road_edges_routing_columns(self, conn):
        expected = {"source", "target", "length_m", "cost_s", "reverse_cost_s"}
        rows = conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema='gis' and table_name='road_edges'"
        ).fetchall()
        found = {r["column_name"] for r in rows}
        missing = expected - found
        assert not missing, f"road_edges missing columns: {missing}"

    def test_routing_function_exists(self, conn):
        row = conn.execute(
            "select count(*) cnt from pg_proc "
            "where proname='route_edges' and "
            "pronamespace=(select oid from pg_namespace where nspname='gis')"
        ).fetchone()
        assert row["cnt"] == 1, "gis.route_edges function not found"

    def test_routing_function_security_invoker(self, conn):
        row = conn.execute(
            "select prosecdef from pg_proc "
            "where proname='route_edges' and "
            "pronamespace=(select oid from pg_namespace where nspname='gis')"
        ).fetchone()
        assert row is not None
        assert not row["prosecdef"], "route_edges must be SECURITY INVOKER"

    def test_spatial_indexes_present(self, conn):
        rows = conn.execute(
            "select count(*) cnt from pg_indexes "
            "where schemaname='gis' and indexname like '%gix%'"
        ).fetchone()
        assert rows["cnt"] >= 5, f"Expected >=5 spatial indexes, found {rows['cnt']}"


@skip_no_db
class TestDataIntegrity:
    """Run only after loaders have been executed."""

    def test_study_areas_nonempty(self, conn):
        row = conn.execute("select count(*) cnt from gis.study_areas").fetchone()
        assert row["cnt"] >= 1, "No study areas loaded"

    def test_road_nodes_nonempty(self, conn):
        row = conn.execute("select count(*) cnt from gis.road_nodes").fetchone()
        assert row["cnt"] >= 100, f"Expected >=100 road nodes, got {row['cnt']}"

    def test_road_edges_nonempty(self, conn):
        row = conn.execute("select count(*) cnt from gis.road_edges").fetchone()
        assert row["cnt"] >= 100, f"Expected >=100 road edges, got {row['cnt']}"

    def test_all_edges_positive_cost(self, conn):
        row = conn.execute(
            "select count(*) cnt from gis.road_edges where cost_s <= 0"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} edges have non-positive cost_s"

    def test_all_edges_positive_length(self, conn):
        row = conn.execute(
            "select count(*) cnt from gis.road_edges where length_m <= 0"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} edges have non-positive length_m"

    def test_edge_source_target_valid(self, conn):
        """All edge source/target node IDs must exist in road_nodes."""
        row = conn.execute("""
            select count(*) cnt from gis.road_edges e
            where not exists (select 1 from gis.road_nodes n where n.id=e.source)
               or not exists (select 1 from gis.road_nodes n where n.id=e.target)
        """).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} edges have dangling source/target"

    def test_no_self_loops(self, conn):
        """Self-loops (source=target) must be absent or intentionally handled."""
        row = conn.execute(
            "select count(*) cnt from gis.road_edges where source=target"
        ).fetchone()
        # Self-loops are not expected in the pilot
        assert row["cnt"] == 0, f"{row['cnt']} self-loop edges found (unexpected)"

    def test_facilities_have_snap_distance(self, conn):
        row = conn.execute(
            "select count(*) cnt from gis.facilities where snap_distance_m is null"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} facilities missing snap_distance_m"

    def test_facility_validation_status_values(self, conn):
        rows = conn.execute(
            "select distinct validation_status from gis.facilities"
        ).fetchall()
        valid = {"candidate", "verified", "excluded"}
        found = {r["validation_status"] for r in rows}
        invalid = found - valid
        assert not invalid, f"Invalid validation_status values: {invalid}"

    def test_population_nonnegative(self, conn):
        row = conn.execute(
            "select count(*) cnt from gis.population_origins where population < 0"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} origins have negative population"

    def test_geoid_12_char(self, conn):
        row = conn.execute(
            "select count(*) cnt from gis.population_origins where length(geoid) != 12"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} origins with non-12-char GEOIDs"

    def test_road_crs_is_wgs84(self, conn):
        """All road geometries should be SRID=4326."""
        row = conn.execute(
            "select count(*) cnt from gis.road_edges "
            "where st_srid(geom) != 4326"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} edges not in SRID 4326"

    def test_processing_runs_no_failure(self, conn):
        rows = conn.execute(
            "select pipeline, error_message from gis.processing_runs where status='failure'"
        ).fetchall()
        failed = [f"{r['pipeline']}: {r['error_message']}" for r in rows]
        assert not failed, f"Processing runs failed:\n" + "\n".join(failed)


@skip_no_db
class TestIdempotency:
    """Re-running loaders must not duplicate rows."""

    def test_study_area_idempotent(self, conn):
        """study_areas must have no duplicate names."""
        row = conn.execute(
            "select count(*) cnt, count(distinct name) cnt_distinct from gis.study_areas"
        ).fetchone()
        assert row["cnt"] == row["cnt_distinct"], "Duplicate study area names found"

    def test_road_nodes_no_duplicates(self, conn):
        """road_nodes PK is natural OSM node ID per area; must be unique."""
        row = conn.execute(
            "select count(*) cnt from ("
            "select id, area_id, count(*) from gis.road_nodes group by id, area_id having count(*)>1"
            ") dups"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} duplicate road_nodes found"

    def test_population_origins_unique_geoid(self, conn):
        row = conn.execute(
            "select count(*) cnt from ("
            "select area_id, geoid, count(*) from gis.population_origins "
            "group by area_id, geoid having count(*)>1"
            ") dups"
        ).fetchone()
        assert row["cnt"] == 0, f"{row['cnt']} duplicate population_origins geoids"
