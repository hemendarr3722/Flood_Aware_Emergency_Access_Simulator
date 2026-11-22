"""
load_census_origins.py — Idempotent loader for Census ACS population origins.

Joins 2024 ACS 5-year B01003_001E (total population) to 2024 Texas TIGER
block-group shapefile by 12-character GEOID, clips to the analysis bbox,
generates point-on-surface as origin point, and snaps to the nearest road node.

Caveats documented per master_prompt:
- Block-group population is not uniformly distributed; point-on-surface is
  the most defensible single-point method without block-level data.
- Partial overlaps from clipping retain the original population estimate
  (do not prorate — the master_prompt prohibits fabricating data).
- Census special negative values (-666666666 etc.) are treated as null/unknown.

Usage:
    python pipelines/load/load_census_origins.py \\
        --area-id 1 \\
        --shapefile data/raw/census/tl_2024_48_bg/tl_2024_48_bg.shp \\
        --population-csv data/raw/census/acs5_2024_population.csv \\
        --config config/study_area.json \\
        --snap-max-m 500 \\
        --confirm-write
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))

CENSUS_SPECIAL_VALUES = {-666666666, -999999999, -888888888, -222222222}


def load_census_origins(
    area_id: int,
    shapefile_path: str,
    population_csv: str,
    config_path: str,
    snap_max_m: float,
    dsn: str,
    dry_run: bool,
) -> dict:
    try:
        import geopandas as gpd
        from shapely.geometry import box
    except ImportError:
        sys.exit("geopandas is required: pip install geopandas")

    with open(config_path) as f:
        cfg = json.load(f)
    bbox = cfg["analysis_bbox_wgs84"]  # [west, south, east, north]
    analysis_crs = cfg["analysis_crs"]  # EPSG:26915

    # ── Load population CSV ───────────────────────────────────────────────────
    pop_map: dict[str, int] = {}
    null_count = 0
    with open(population_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = str(row.get("GEOID") or row.get("geoid") or "").strip()
            if len(geoid) != 12:
                continue
            raw_pop = row.get("B01003_001E") or row.get("population") or row.get("pop")
            if raw_pop is None:
                null_count += 1
                continue
            try:
                pop_val = int(float(raw_pop))
            except (ValueError, TypeError):
                null_count += 1
                continue
            if pop_val in CENSUS_SPECIAL_VALUES or pop_val < 0:
                null_count += 1
                continue
            pop_map[geoid] = pop_val
    print(f"Population CSV: {len(pop_map)} valid GEOIDs, {null_count} null/special-value GEOIDs")

    # ── Load TIGER shapefile and clip to bbox ─────────────────────────────────
    gdf = gpd.read_file(shapefile_path)
    if gdf.crs is None or str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    study_box = box(bbox[0], bbox[1], bbox[2], bbox[3])
    gdf_clipped = gdf[gdf.geometry.intersects(study_box)].copy()
    print(f"TIGER block groups: {len(gdf)} total TX, {len(gdf_clipped)} intersecting pilot bbox")

    # Normalize GEOID field
    geoid_col = None
    for col in ("GEOID", "GEOID20", "GEOID10", "geoid"):
        if col in gdf_clipped.columns:
            geoid_col = col
            break
    if geoid_col is None:
        sys.exit("No GEOID column found in shapefile")
    gdf_clipped["geoid_12"] = gdf_clipped[geoid_col].astype(str).str.strip()

    # Validate 12-character GEOIDs
    invalid_geoid = gdf_clipped[gdf_clipped["geoid_12"].str.len() != 12]
    if len(invalid_geoid):
        print(f"WARNING: {len(invalid_geoid)} block groups with non-12-char GEOIDs — skipped")
    gdf_clipped = gdf_clipped[gdf_clipped["geoid_12"].str.len() == 12]

    # Join population
    gdf_clipped["population"] = gdf_clipped["geoid_12"].map(pop_map)
    no_pop = gdf_clipped["population"].isna().sum()
    print(f"Joined: {(~gdf_clipped['population'].isna()).sum()} block groups with population, {no_pop} without")

    # Drop rows with no population data
    gdf_valid = gdf_clipped[gdf_clipped["population"].notna()].copy()
    gdf_valid["population"] = gdf_valid["population"].astype(int)

    # Generate point-on-surface (avoids centroid falling outside polygon)
    import shapely
    gdf_proj = gdf_valid.to_crs(analysis_crs)
    gdf_proj["origin_point"] = gpd.GeoSeries(
        shapely.point_on_surface(gdf_proj.geometry.values),
        crs=gdf_proj.crs,
        index=gdf_proj.index,
    )
    gdf_valid["origin_wgs84"] = gdf_proj["origin_point"].to_crs("EPSG:4326")

    total_pop = gdf_valid["population"].sum()
    print(
        f"Origins: {len(gdf_valid)} block groups, "
        f"total modeled population={total_pop:,}\n"
        "NOTE: Partial bbox overlaps retain original block-group population (not prorated).\n"
        "NOTE: Point-on-surface is used; population is not uniformly distributed within BGs."
    )

    if dry_run:
        print("DRY RUN — no database changes. Pass --confirm-write to load.")
        return {"block_groups": len(gdf_valid), "total_population": int(total_pop)}

    counts = {
        "inserted": 0, "skipped_duplicate": 0,
        "excluded_snap": 0, "total_population": int(total_pop),
    }

    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        conn.execute(
            "insert into gis.processing_runs(pipeline, area_id, status) values(%s,%s,'running')",
            ("load_census_origins", area_id),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("load_census_origins",),
        ).fetchone()["id"]

        try:
            existing_geoids = {
                r["geoid"]
                for r in conn.execute(
                    "select geoid from gis.population_origins where area_id=%s", (area_id,)
                ).fetchall()
            }

            for _, row in gdf_valid.iterrows():
                geoid = row["geoid_12"]
                if geoid in existing_geoids:
                    counts["skipped_duplicate"] += 1
                    continue

                pt = row["origin_wgs84"]
                x, y = pt.x, pt.y
                pop = int(row["population"])

                # Snap to nearest road node (projected distance in metres)
                snap_row = conn.execute(
                    """
                    select
                        n.id as node_id,
                        st_distance(
                            st_transform(n.geom, 26915),
                            st_transform(
                                st_setsrid(st_makepoint(%s,%s), 4326),
                                26915
                            )
                        ) as dist_m
                    from gis.road_nodes n
                    where n.area_id = %s
                    order by n.geom <-> st_setsrid(st_makepoint(%s,%s), 4326)
                    limit 1
                    """,
                    (x, y, area_id, x, y),
                ).fetchone()

                if snap_row is None:
                    print(f"WARNING: No road nodes for area_id={area_id}; skipping origin {geoid}")
                    continue

                snap_dist_m = float(snap_row["dist_m"])
                node_id = snap_row["node_id"]
                snap_valid = snap_dist_m <= snap_max_m

                conn.execute(
                    """insert into gis.population_origins(
                        area_id, geoid, population, geom,
                        road_node_id, snap_distance_m, snap_max_m, snap_valid, population_year
                    ) values (%s,%s,%s,
                        st_setsrid(st_makepoint(%s,%s), 4326),
                        %s,%s,%s,%s, 2024)
                    on conflict (area_id, geoid) do nothing
                    """,
                    (area_id, geoid, pop, x, y, node_id, snap_dist_m, snap_max_m, snap_valid),
                )

                if snap_valid:
                    counts["inserted"] += 1
                else:
                    counts["excluded_snap"] += 1

            print(
                f"Origins: {counts['inserted']} inserted (snap valid), "
                f"{counts['excluded_snap']} inserted (snap beyond max), "
                f"{counts['skipped_duplicate']} skipped duplicate"
            )

            conn.execute(
                "update gis.processing_runs set status='success', finished_at=now(), "
                "row_counts=%s where id=%s",
                (json.dumps(counts), run_id),
            )
            conn.commit()

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
    p.add_argument("--area-id", type=int, required=True)
    p.add_argument("--shapefile", default="data/raw/census/tl_2024_48_bg/tl_2024_48_bg.shp")
    p.add_argument("--population-csv", default="data/raw/census/acs5_2024_population.csv")
    p.add_argument("--config", default="config/study_area.json")
    p.add_argument("--snap-max-m", type=float, default=500.0)
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    load_census_origins(
        area_id=args.area_id,
        shapefile_path=args.shapefile,
        population_csv=args.population_csv,
        config_path=args.config,
        snap_max_m=args.snap_max_m,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
