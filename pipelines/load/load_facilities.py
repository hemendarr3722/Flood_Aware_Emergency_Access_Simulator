"""
load_facilities.py — Idempotent loader for candidate emergency facilities.

Reads the raw OSM facilities GeoJSON. Snaps each facility to the nearest
drivable road node using EPSG:26915 (metres). Facilities beyond snap_max_m
are marked 'excluded' rather than force-snapped.

No OSM facility tag proves current emergency or shelter operations.
All loaded facilities start as 'candidate' status.

Usage:
    python pipelines/load/load_facilities.py \\
        --area-id 1 \\
        --facilities data/raw/osm/facilities.geojson \\
        --snap-max-m 300 \\
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

# Map OSM amenity tags to our allowed facility_type values
AMENITY_TO_TYPE: dict[str, str] = {
    "hospital": "hospital",
    "fire_station": "fire_station",
    "clinic": "hospital",        # grouped as hospital class
    "doctors": "hospital",
    "police": "fire_station",    # grouped as fire_station class (emergency response)
    "shelter": "shelter",
}

SNAP_MAX_M_DEFAULT = 300.0


def load_facilities(
    area_id: int,
    facilities_path: str,
    snap_max_m: float,
    dsn: str,
    dry_run: bool,
) -> dict:
    with open(facilities_path) as f:
        fc = json.load(f)

    features = fc.get("features", [])
    print(f"Input: {len(features)} facility features")

    parsed: list[dict] = []
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        amenity = props.get("amenity", "")
        if isinstance(amenity, list):
            amenity = amenity[0] if amenity else ""
        facility_type = AMENITY_TO_TYPE.get(amenity)
        if facility_type is None:
            continue  # skip non-emergency amenities

        if geom.get("type") not in ("Point", "Polygon", "MultiPolygon"):
            continue
        if geom["type"] == "Point":
            x, y = geom["coordinates"]
        else:
            # Use representative point: compute centroid of first exterior ring
            ring = geom["coordinates"][0]
            if isinstance(ring[0][0], list):
                ring = ring[0]
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            x = sum(xs) / len(xs)
            y = sum(ys) / len(ys)

        name = props.get("name") or props.get("name:en")
        if not isinstance(name, str) or not name.strip():
            name = f"Unnamed {facility_type.replace('_', ' ').title()}"

        # Build stable osm_id from feature index or id properties
        osm_id = str(props.get("osmid") or props.get("@id") or props.get("id") or "")
        parsed.append({"osm_id": osm_id, "name": name, "type": facility_type, "x": x, "y": y})

    print(f"Parsed {len(parsed)} valid emergency facilities (hospital/fire_station/shelter)")

    if dry_run:
        for f in parsed:
            print(f"  {f['type']:15s} {f['name'][:40]}")
        print("DRY RUN — no database changes. Pass --confirm-write to load.")
        return {"parsed": len(parsed)}

    counts = {"inserted": 0, "skipped_duplicate": 0, "excluded_snap": 0}

    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        conn.execute(
            "insert into gis.processing_runs(pipeline, area_id, status) values(%s,%s,'running')",
            ("load_facilities", area_id),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("load_facilities",),
        ).fetchone()["id"]

        try:
            existing_osm_ids = {
                r["osm_id"]
                for r in conn.execute(
                    "select osm_id from gis.facilities where area_id=%s", (area_id,)
                ).fetchall()
            }

            for fac in parsed:
                osm_id = fac["osm_id"]
                if osm_id and osm_id in existing_osm_ids:
                    counts["skipped_duplicate"] += 1
                    continue

                x, y = fac["x"], fac["y"]
                # Snap to nearest road node using PostGIS <-> operator (geographic distance)
                # We use ST_Distance in EPSG:26915 for the actual distance check
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
                    print(f"WARNING: No road nodes found for area_id={area_id}; cannot snap facility")
                    continue

                snap_dist_m = float(snap_row["dist_m"])
                node_id = snap_row["node_id"]

                if snap_dist_m > snap_max_m:
                    # Mark as excluded, record why
                    conn.execute(
                        """insert into gis.facilities(
                            area_id, osm_id, name, facility_type, geom,
                            road_node_id, snap_distance_m, snap_max_m,
                            validation_status, exclusion_reason, is_active
                        ) values (%s,%s,%s,%s,
                            st_setsrid(st_makepoint(%s,%s), 4326),
                            %s,%s,%s,'excluded',%s,false)
                        on conflict do nothing
                        """,
                        (
                            area_id, osm_id, fac["name"], fac["type"],
                            x, y,
                            node_id, snap_dist_m, snap_max_m,
                            f"Snap distance {snap_dist_m:.1f}m exceeds max {snap_max_m}m",
                        ),
                    )
                    counts["excluded_snap"] += 1
                    print(f"  EXCLUDED (snap={snap_dist_m:.0f}m > {snap_max_m}m): {fac['name']}")
                else:
                    conn.execute(
                        """insert into gis.facilities(
                            area_id, osm_id, name, facility_type, geom,
                            road_node_id, snap_distance_m, snap_max_m,
                            validation_status, is_active
                        ) values (%s,%s,%s,%s,
                            st_setsrid(st_makepoint(%s,%s), 4326),
                            %s,%s,%s,'candidate',true)
                        on conflict do nothing
                        """,
                        (
                            area_id, osm_id, fac["name"], fac["type"],
                            x, y,
                            node_id, snap_dist_m, snap_max_m,
                        ),
                    )
                    counts["inserted"] += 1
                    print(f"  CANDIDATE (snap={snap_dist_m:.0f}m): {fac['type']:15s} {fac['name']}")

            print(
                f"\nFacilities: {counts['inserted']} candidate, "
                f"{counts['excluded_snap']} excluded (snap), "
                f"{counts['skipped_duplicate']} skipped duplicate"
            )
            print("IMPORTANT: OSM facility tags do not prove current emergency operations.")
            print("           Review and update validation_status before analysis.")

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
    p.add_argument("--facilities", default="data/raw/osm/facilities.geojson")
    p.add_argument("--snap-max-m", type=float, default=SNAP_MAX_M_DEFAULT)
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    load_facilities(
        area_id=args.area_id,
        facilities_path=args.facilities,
        snap_max_m=args.snap_max_m,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
