"""
run_all_loaders.py — Orchestrates Phase 2 loaders in correct dependency order.

Requires: DATABASE_URL env var pointing to a fresh migrated database.
Run from project root directory.

Order:
  1. load_study_area.py      → creates study area record → returns area_id
  2. load_osm_network.py     → loads road nodes and edges
  3. load_facilities.py      → snaps facilities to road nodes
  4. load_fema_hazard.py     → loads FEMA flood-zone polygons (staging)
  5. load_census_origins.py  → joins ACS + TIGER, snaps to road nodes

Usage:
    python pipelines/load/run_all_loaders.py --confirm-write
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run(cmd: list[str], desc: str) -> None:
    print(f"\n{'='*60}")
    print(f"STEP: {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(f"FAILED: {desc}")


def get_area_id(dsn: str, name: str) -> int:
    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "select id from gis.study_areas where name=%s", (name,)
        ).fetchone()
    if row is None:
        sys.exit(f"Study area '{name}' not found in database after load_study_area")
    return row["id"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm-write", action="store_true",
                   help="Actually write to database (dry run without this flag)")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL env var is required")

    cfg_path = str(ROOT / "config" / "study_area.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    area_name = cfg["name"]

    flags = ["--confirm-write"] if args.confirm_write else []

    # Step 1: Study area
    run(
        [PYTHON, "pipelines/load/load_study_area.py",
         "--config", cfg_path,
         "--boundary", "data/raw/osm/study_area.geojson"] + flags,
        "Load study area",
    )

    if not args.confirm_write:
        print("\nDRY RUN complete. Add --confirm-write to actually load data.")
        return

    area_id = get_area_id(dsn, area_name)
    print(f"Using area_id={area_id}")

    # Step 2: Road network
    run(
        [PYTHON, "pipelines/load/load_osm_network.py",
         "--area-id", str(area_id),
         "--nodes", "data/raw/osm/road_nodes.geojson",
         "--edges", "data/raw/osm/road_edges.geojson",
         "--confirm-write"],
        "Load OSM road network",
    )

    # Step 3: Facilities (requires road nodes)
    run(
        [PYTHON, "pipelines/load/load_facilities.py",
         "--area-id", str(area_id),
         "--facilities", "data/raw/osm/facilities.geojson",
         "--snap-max-m", "300",
         "--confirm-write"],
        "Load facilities",
    )

    # Step 4: FEMA hazard polygons
    fema_path = "data/raw/fema_nfhl/fema_nfhl_flood_hazard_zones.geojson"
    if Path(ROOT / fema_path).exists():
        run(
            [PYTHON, "pipelines/load/load_fema_hazard.py",
             "--area-id", str(area_id),
             "--fema-geojson", fema_path,
             "--confirm-write"],
            "Load FEMA flood-hazard zones",
        )
    else:
        print(f"\nSKIPPING FEMA: {fema_path} not found")

    # Step 5: Census origins (requires road nodes)
    run(
        [PYTHON, "pipelines/load/load_census_origins.py",
         "--area-id", str(area_id),
         "--shapefile", "data/raw/census/tl_2024_48_bg/tl_2024_48_bg.shp",
         "--population-csv", "data/raw/census/acs5_2024_population.csv",
         "--config", cfg_path,
         "--snap-max-m", "500",
         "--confirm-write"],
        "Load Census population origins",
    )

    print("\n" + "="*60)
    print("ALL LOADERS COMPLETE")
    print("="*60)
    print(f"Run database/verify.sql to validate the database state.")


if __name__ == "__main__":
    main()
