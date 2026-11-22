"""
load_study_area.py — Idempotent loader for the study area record.

Reads config/study_area.json and the OSM study_area.geojson boundary.
If a study area with the same name already exists, it updates the boundary.

Usage:
    python pipelines/load/load_study_area.py \\
        --config config/study_area.json \\
        --boundary data/raw/osm/study_area.geojson \\
        --confirm-write
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))

def load_study_area(config_path: str, boundary_path: str, dsn: str, dry_run: bool) -> int:
    """Insert or update study area. Returns area_id."""
    with open(config_path) as f:
        cfg = json.load(f)

    name: str = cfg["name"]
    bbox = cfg["analysis_bbox_wgs84"]  # [west, south, east, north]

    # Build a MultiPolygon WKT from bbox as fallback if no boundary file
    boundary_wkt: str | None = None
    if boundary_path and Path(boundary_path).exists():
        with open(boundary_path) as f:
            fc = json.load(f)
        # Take first feature geometry
        for feat in fc.get("features", []):
            geom = feat.get("geometry", {})
            gtype = geom.get("type", "")
            coords = geom.get("coordinates")
            if coords and gtype in ("Polygon", "MultiPolygon"):
                boundary_wkt = f"SRID=4326;MULTIPOLYGON{_coords_to_wkt(coords, gtype)}"
                break
        if boundary_wkt is None:
            # fall back to bbox rectangle
            w, s, e, n = bbox
            boundary_wkt = (
                f"SRID=4326;MULTIPOLYGON((({w} {s},{e} {s},{e} {n},{w} {n},{w} {s})))"
            )
    else:
        w, s, e, n = bbox
        boundary_wkt = (
            f"SRID=4326;MULTIPOLYGON((({w} {s},{e} {s},{e} {n},{w} {n},{w} {s})))"
        )

    print(f"Study area: {name!r}")
    print(f"Boundary WKT prefix: {boundary_wkt[:80]}...")

    if dry_run:
        print("DRY RUN — no database changes. Pass --confirm-write to load.")
        return -1

    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        # Record processing run
        conn.execute(
            "insert into gis.processing_runs(pipeline, status) values(%s,'running')",
            ("load_study_area",),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("load_study_area",),
        ).fetchone()["id"]

        try:
            existing = conn.execute(
                "select id from gis.study_areas where name=%s", (name,)
            ).fetchone()

            if existing:
                area_id = existing["id"]
                conn.execute(
                    "update gis.study_areas set boundary=st_geomfromewkt(%s) where id=%s",
                    (boundary_wkt, area_id),
                )
                print(f"Updated existing study area id={area_id}")
            else:
                row = conn.execute(
                    "insert into gis.study_areas(name,boundary) values(%s,st_geomfromewkt(%s)) returning id",
                    (name, boundary_wkt),
                ).fetchone()
                area_id = row["id"]
                print(f"Inserted new study area id={area_id}")

            conn.execute(
                "update gis.processing_runs set status='success', finished_at=now(), "
                "row_counts=%s where id=%s",
                (json.dumps({"study_areas": 1}), run_id),
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

    return area_id


def _coords_to_wkt(coords: list, gtype: str) -> str:
    """Convert GeoJSON coordinate lists to WKT interior for MultiPolygon."""
    if gtype == "Polygon":
        rings = ",".join(_ring_wkt(r) for r in coords)
        return f"(({rings}))"
    elif gtype == "MultiPolygon":
        polys = []
        for poly_coords in coords:
            rings = ",".join(_ring_wkt(r) for r in poly_coords)
            polys.append(f"({rings})")
        return "(" + ",".join(polys) + ")"
    return ""


def _ring_wkt(ring: list) -> str:
    return "(" + ",".join(f"{x} {y}" for x, y in ring) + ")"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config/study_area.json")
    p.add_argument("--boundary", default="data/raw/osm/study_area.geojson")
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL env var is required for --confirm-write")

    area_id = load_study_area(
        config_path=args.config,
        boundary_path=args.boundary,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )
    if area_id >= 0:
        print(f"area_id={area_id}")


if __name__ == "__main__":
    main()
