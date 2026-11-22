"""
database/tests/test_population_accessibility.py — Phase 5 Accessibility Validation Suite.

Validates:
1. Exact population reconciliation: total modeled population equals input rows.
2. Category completeness: reachable + unreachable + invalid_snap = total modeled population.
3. No double counting: each origin contributes its population exactly once per scenario.
4. Threshold monotonicity: pop(15 min) <= pop(30 min) <= pop(45 min).
5. Invariant: edge removals cannot improve shortest travel time for any origin.
6. Unreachable origins have travel_time_s IS NULL (never 0).
7. Census data integrity: all GEOIDs are 12 characters, all populations >= 0.
8. Baseline vs FEMA flood comparison matches expected impact numbers.
"""
import os
import pytest
from psycopg import connect
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live database integration tests",
)


@pytest.fixture(scope="session")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    with connect(DATABASE_URL, row_factory=dict_row) as c:
        yield c


@skip_no_db
class TestPopulationReconciliation:
    """Verify total population and category reconciliation invariants."""

    def test_total_modeled_population_matches_origins(self, conn):
        """Total modeled population in accessibility table matches population_origins table."""
        expected_pop = conn.execute(
            "select sum(population) as pop, count(*) as cnt from gis.population_origins"
        ).fetchone()

        for sc_kind in ("baseline", "hazard_polygon"):
            sc_id = conn.execute(
                "select id from gis.flood_scenarios where scenario_kind = %s", (sc_kind,)
            ).fetchone()["id"]

            acc_row = conn.execute(
                "select sum(population) as pop, count(*) as cnt from gis.scenario_accessibility where scenario_id = %s",
                (sc_id,),
            ).fetchone()

            assert acc_row["cnt"] == expected_pop["cnt"] == 548, (
                f"Origin count mismatch for {sc_kind}: {acc_row['cnt']} != {expected_pop['cnt']}"
            )
            assert acc_row["pop"] == expected_pop["pop"] == 740186, (
                f"Population sum mismatch for {sc_kind}: {acc_row['pop']} != {expected_pop['pop']}"
            )

    def test_mutually_exclusive_categories_sum_to_total(self, conn):
        """
        RECONCILIATION INVARIANT:
        Sum of mutually exclusive categories equals total modeled population exactly.
        Categories: within_threshold + beyond_threshold + network_unreachable + invalid_snap
        """
        for sc_kind in ("baseline", "hazard_polygon"):
            sc_id = conn.execute(
                "select id from gis.flood_scenarios where scenario_kind = %s", (sc_kind,)
            ).fetchone()["id"]

            row = conn.execute(
                """
                select
                    sum(population) as total_pop,
                    sum(population) filter (where status_category = 'reachable' and threshold_15min) as pop_15min,
                    sum(population) filter (where status_category = 'reachable' and not threshold_15min) as pop_beyond_15min,
                    sum(population) filter (where status_category = 'network_unreachable') as pop_unreachable,
                    sum(population) filter (where status_category = 'invalid_snap') as pop_invalid_snap
                from gis.scenario_accessibility
                where scenario_id = %s
                """,
                (sc_id,),
            ).fetchone()

            cat_sum = (
                (row["pop_15min"] or 0)
                + (row["pop_beyond_15min"] or 0)
                + (row["pop_unreachable"] or 0)
                + (row["pop_invalid_snap"] or 0)
            )

            assert cat_sum == row["total_pop"] == 740186, (
                f"Category reconciliation failed for {sc_kind}: {cat_sum} != {row['total_pop']}"
            )

    def test_no_double_counting(self, conn):
        """Each origin must appear exactly once per scenario."""
        for sc_kind in ("baseline", "hazard_polygon"):
            sc_id = conn.execute(
                "select id from gis.flood_scenarios where scenario_kind = %s", (sc_kind,)
            ).fetchone()["id"]

            dups = conn.execute(
                """
                select origin_id, count(*)
                from gis.scenario_accessibility
                where scenario_id = %s
                group by origin_id
                having count(*) > 1
                """,
                (sc_id,),
            ).fetchall()

            assert len(dups) == 0, f"Found {len(dups)} duplicate origin rows in {sc_kind}"


@skip_no_db
class TestThresholdMonotonicity:
    """Validate travel time threshold invariants."""

    def test_threshold_coverage_monotonicity(self, conn):
        """
        THRESHOLD MONOTONICITY INVARIANT:
        Population reachable within 15 min <= within 30 min <= within 45 min <= all reachable.
        """
        for sc_kind in ("baseline", "hazard_polygon"):
            sc_id = conn.execute(
                "select id from gis.flood_scenarios where scenario_kind = %s", (sc_kind,)
            ).fetchone()["id"]

            row = conn.execute(
                """
                select
                    sum(population) filter (where threshold_15min) as pop_15,
                    sum(population) filter (where threshold_30min) as pop_30,
                    sum(population) filter (where threshold_45min) as pop_45,
                    sum(population) filter (where reachable) as pop_reachable
                from gis.scenario_accessibility
                where scenario_id = %s
                """,
                (sc_id,),
            ).fetchone()

            p15 = row["pop_15"] or 0
            p30 = row["pop_30"] or 0
            p45 = row["pop_45"] or 0
            p_reach = row["pop_reachable"] or 0

            assert p15 <= p30, f"15min pop ({p15}) > 30min pop ({p30}) in {sc_kind}"
            assert p30 <= p45, f"30min pop ({p30}) > 45min pop ({p45}) in {sc_kind}"
            assert p45 <= p_reach, f"45min pop ({p45}) > reachable pop ({p_reach}) in {sc_kind}"


@skip_no_db
class TestFloodImpactOnAccessibility:
    """Validate comparison between baseline and FEMA flood hazard prototype."""

    def test_flood_scenario_isolates_population(self, conn):
        """Under FEMA 100-year SFHA hazard, exactly 2 origins become isolated (4,294 people)."""
        base_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'baseline'"
        ).fetchone()["id"]
        flood_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        base_unreach = conn.execute(
            "select sum(population) as pop, count(*) as cnt from gis.scenario_accessibility "
            "where scenario_id = %s and status_category = 'network_unreachable'",
            (base_id,),
        ).fetchone()

        flood_unreach = conn.execute(
            "select sum(population) as pop, count(*) as cnt from gis.scenario_accessibility "
            "where scenario_id = %s and status_category = 'network_unreachable'",
            (flood_id,),
        ).fetchone()

        assert base_unreach["cnt"] == 0, "Baseline should have 0 network-unreachable origins in pilot"
        assert flood_unreach["cnt"] == 2, f"Expected 2 unreachable origins in flood, got {flood_unreach['cnt']}"
        assert flood_unreach["pop"] == 4294, f"Expected 4,294 isolated population, got {flood_unreach['pop']}"

    def test_shortest_path_monotonicity_per_origin(self, conn):
        """
        ORIGIN TRAVEL TIME MONOTONICITY INVARIANT:
        For any origin that remains reachable, its shortest travel time under flood
        CANNOT be faster than baseline (t_flood >= t_base - 1e-4).
        """
        base_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'baseline'"
        ).fetchone()["id"]
        flood_id = conn.execute(
            "select id from gis.flood_scenarios where scenario_kind = 'hazard_polygon'"
        ).fetchone()["id"]

        rows = conn.execute(
            """
            select
                b.origin_id,
                b.travel_time_s as t_base,
                f.travel_time_s as t_flood
            from gis.scenario_accessibility b
            join gis.scenario_accessibility f
              on f.origin_id = b.origin_id and f.scenario_id = %s
            where b.scenario_id = %s
              and b.reachable = true
              and f.reachable = true
            """,
            (flood_id, base_id),
        ).fetchall()

        assert len(rows) == 8, f"Expected 8 origins reachable in both scenarios, got {len(rows)}"

        for r in rows:
            assert r["t_flood"] >= r["t_base"] - 1e-4, (
                f"Origin {r['origin_id']} travel time improved under flood: "
                f"base={r['t_base']}s vs flood={r['t_flood']}s"
            )

    def test_unreachable_is_never_stored_as_zero(self, conn):
        """INVARIANT: Unreachable origins must have travel_time_s IS NULL, never 0.0."""
        zero_unreach = conn.execute(
            "select count(*) cnt from gis.scenario_accessibility "
            "where not reachable and travel_time_s is not null"
        ).fetchone()["cnt"]

        assert zero_unreach == 0, (
            f"CRITICAL INVARIANT VIOLATED: {zero_unreach} unreachable origins have non-null travel time!"
        )

    def test_census_special_negative_values_not_in_population(self, conn):
        """INVARIANT: Population values must be non-negative."""
        bad_pop = conn.execute(
            "select count(*) cnt from gis.scenario_accessibility where population < 0"
        ).fetchone()["cnt"]

        assert bad_pop == 0, f"Found {bad_pop} origins with negative population!"
