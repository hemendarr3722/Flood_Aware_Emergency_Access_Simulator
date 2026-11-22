"""
compute_hazard_impacts.py — Track A: FEMA SFHA Hazard-Polygon Impact Model.

Computes road edge intersections with FEMA National Flood Hazard Layer (NFHL)
Special Flood Hazard Area (SFHA, 100-year / 1% annual chance) zones.

Transparent modeling rule:
  "Road edges intersecting FEMA NFHL Special Flood Hazard Area (1% annual-chance / 100-year)
   zones are modeled as potentially affected and excluded from emergency routes in this
   planning scenario."

Labels:
  Results are explicitly labeled 'modeled potentially affected roads'.
  They are NOT 'observed closed', 'inundated', or 'depth-based'.

Usage:
    python pipelines/transform/compute_hazard_impacts.py --area-id 1 --confirm-write
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))

from psycopg import connect
from psycopg.rows import dict_row

SCENARIO_NAME = "FEMA 100-Year SFHA Hazard Prototype"
SCENARIO_DESCRIPTION = (
    "Modeled potentially affected roads intersecting FEMA Special Flood Hazard Area "
    "(SFHA, 1% annual chance / 100-year) zones (A, AE, AO). "
    "Planning demonstration only; regulatory hazard zones, NOT observed real-world "
    "road closures or water depth."
)
ALGORITHM_VERSION = "v1.0.0-fema-sfha-intersect"


def compute_fema_impacts(area_id: int, dsn: str, dry_run: bool) -> dict:
    with connect(dsn, row_factory=dict_row) as conn:
        # Check available FEMA zones
        sfha_count = conn.execute(
            "select count(*) cnt from gis.fema_flood_zones where area_id = %s and sfha_tf = 'T'",
            (area_id,),
        ).fetchone()["cnt"]

        if sfha_count == 0:
            sys.exit(f"No SFHA flood zones found in gis.fema_flood_zones for area_id={area_id}")

        print(f"Found {sfha_count} SFHA polygon features in staging table")

        # Intersect road edges with SFHA zones using projected CRS EPSG:26915 for length
        # Aggregate multiple intersecting zones per edge (take primary zone and total length)
        impact_rows = conn.execute(
            """
            with edge_zone_intersections as (
                select
                    e.id as edge_id,
                    e.length_m as edge_length_m,
                    z.fld_zone,
                    z.sfha_tf,
                    z.source_feature_id,
                    st_length(st_transform(st_intersection(e.geom, z.geom), 26915)) as intersect_len_m
                from gis.road_edges e
                join gis.fema_flood_zones z
                  on z.area_id = e.area_id
                 and z.sfha_tf = 'T'
                 and st_intersects(e.geom, z.geom)
                where e.area_id = %s
            ),
            aggregated as (
                select
                    edge_id,
                    edge_length_m,
                    (array_agg(fld_zone order by intersect_len_m desc))[1] as primary_zone,
                    'T' as sfha_tf,
                    string_agg(distinct source_feature_id, ',') as source_feature_ids,
                    sum(intersect_len_m) as total_intersect_len_m
                from edge_zone_intersections
                group by edge_id, edge_length_m
            )
            select
                edge_id,
                primary_zone,
                sfha_tf,
                source_feature_ids,
                total_intersect_len_m,
                least(1.0, greatest(0.0, total_intersect_len_m / nullif(edge_length_m, 0))) as intersection_fraction
            from aggregated
            where total_intersect_len_m > 0.1
            order by edge_id;
            """,
            (area_id,),
        ).fetchall()

        print(f"Computed {len(impact_rows)} intersecting road edges")
        avg_fraction = (
            sum(r["intersection_fraction"] for r in impact_rows) / len(impact_rows)
            if impact_rows else 0
        )
        print(f"Average intersection fraction: {avg_fraction * 100:.1f}%")

        if dry_run:
            print("DRY RUN — no changes written. Pass --confirm-write to commit.")
            return {"affected_edges": len(impact_rows)}

        # Record processing run
        conn.execute(
            "insert into gis.processing_runs(pipeline, area_id, status) values(%s, %s, 'running')",
            ("compute_hazard_impacts", area_id),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("compute_hazard_impacts",),
        ).fetchone()["id"]

        try:
            # Upsert scenario
            conn.execute(
                """
                insert into gis.flood_scenarios (
                    area_id, name, description, scenario_kind, threshold_m,
                    status, algorithm_version
                ) values (%s, %s, %s, 'hazard_polygon', 0.0, 'ready', %s)
                on conflict (area_id, name) do update
                set description = excluded.description,
                    scenario_kind = excluded.scenario_kind,
                    threshold_m = excluded.threshold_m,
                    status = excluded.status,
                    algorithm_version = excluded.algorithm_version
                returning id
                """,
                (area_id, SCENARIO_NAME, SCENARIO_DESCRIPTION, ALGORITHM_VERSION),
            )
            scenario_id = conn.execute(
                "select id from gis.flood_scenarios where area_id=%s and name=%s",
                (area_id, SCENARIO_NAME),
            ).fetchone()["id"]

            print(f"Scenario ID: {scenario_id} ({SCENARIO_NAME})")

            # Replace scenario impacts
            conn.execute(
                "delete from gis.scenario_edge_impacts where scenario_id = %s",
                (scenario_id,),
            )

            # Insert impacts
            with conn.cursor().copy(
                """
                copy gis.scenario_edge_impacts(
                    scenario_id, edge_id, is_closed, impact_kind,
                    intersection_fraction, flood_zone, sfha_tf, source_feature_id
                ) from stdin
                """
            ) as cp:
                for r in impact_rows:
                    cp.write_row((
                        scenario_id,
                        r["edge_id"],
                        True,  # Modeled potentially affected (closed in routing graph)
                        "hazard_polygon",
                        round(float(r["intersection_fraction"]), 4),
                        r["primary_zone"],
                        r["sfha_tf"],
                        str(r["source_feature_ids"] or "")[:100],
                    ))

            counts = {
                "scenario_id": scenario_id,
                "affected_edges": len(impact_rows),
                "rule": "Edges intersecting FEMA SFHA 100-year flood zones are modeled as potentially affected.",
                "disclaimer": "Regulatory hazard information, NOT current inundation or water depth.",
            }

            conn.execute(
                "update gis.processing_runs set status='success', finished_at=now(), "
                "row_counts=%s where id=%s",
                (json.dumps(counts), run_id),
            )
            conn.commit()
            print(f"Successfully committed {len(impact_rows)} hazard impacts to scenario {scenario_id}.")

        except Exception as exc:
            conn.execute(
                "update gis.processing_runs set status='failure', finished_at=now(), "
                "error_message=%s where id=%s",
                (str(exc), run_id),
            )
            conn.commit()
            raise

    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--area-id", type=int, default=1)
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    compute_fema_impacts(
        area_id=args.area_id,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
