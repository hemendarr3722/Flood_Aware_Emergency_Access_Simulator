"""
load_fema_hazard.py — Idempotent loader for FEMA NFHL flood-hazard polygons.

Loads raw FEMA flood-zone polygons into gis.fema_flood_zones (staging table).
Does NOT intersect with roads — that is a Phase 4 task.

IMPORTANT: FEMA NFHL polygons are regulatory flood-hazard zones.
           They are NOT current inundation and NOT water depth.
           They must NOT be described as actual flood events.

Usage:
    python pipelines/load/load_fema_hazard.py \\
        --area-id 1 \\
        --fema-geojson data/raw/fema_nfhl/fema_nfhl_flood_hazard_zones.geojson \\
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

# SFHA = Special Flood Hazard Area (100-year flood zone)
SFHA_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}


def load_fema(
    area_id: int,
    fema_path: str,
    dsn: str,
    dry_run: bool,
) -> dict:
    with open(fema_path) as f:
        fc = json.load(f)

    features = fc.get("features", [])
    print(f"Input: {len(features)} FEMA flood-zone features")

    parsed: list[dict] = []
    invalid_geom = 0
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})

        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            invalid_geom += 1
            continue

        fld_zone = str(props.get("FLD_ZONE") or props.get("fld_zone") or "").strip()
        sfha_tf = str(props.get("SFHA_TF") or props.get("sfha_tf") or "").strip()
        dfirm_id = str(props.get("DFIRM_ID") or props.get("dfirm_id") or "").strip()
        zone_subtype = str(props.get("ZONE_SUBTY") or props.get("zone_subty") or "").strip()
        source_id = str(props.get("FID") or props.get("OBJECTID") or props.get("id") or "")

        # Build WKT from GeoJSON geometry
        gtype = geom["type"]
        coords = geom["coordinates"]
        wkt = _geojson_to_wkt(gtype, coords)

        parsed.append({
            "fld_zone": fld_zone,
            "sfha_tf": sfha_tf,
            "dfirm_id": dfirm_id,
            "zone_subtype": zone_subtype,
            "source_id": source_id,
            "wkt": wkt,
        })

    sfha_count = sum(1 for p in parsed if p["sfha_tf"].upper() == "T")
    print(
        f"Parsed {len(parsed)} valid polygon features "
        f"({sfha_count} SFHA, {invalid_geom} invalid/skipped geometry)"
    )

    if dry_run:
        # Print distribution of flood zones
        zone_dist: dict[str, int] = {}
        for p in parsed:
            zone_dist[p["fld_zone"]] = zone_dist.get(p["fld_zone"], 0) + 1
        for zone, cnt in sorted(zone_dist.items(), key=lambda x: -x[1])[:10]:
            print(f"  FLD_ZONE={zone!r:10s}: {cnt}")
        print("DRY RUN — no database changes. Pass --confirm-write to load.")
        return {"parsed": len(parsed), "sfha": sfha_count}

    counts = {"inserted": 0, "skipped": 0}

    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        conn.execute(
            "insert into gis.processing_runs(pipeline, area_id, status) values(%s,%s,'running')",
            ("load_fema_hazard", area_id),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("load_fema_hazard",),
        ).fetchone()["id"]

        try:
            # Idempotent: delete existing records for this area then reload
            existing = conn.execute(
                "select count(*) cnt from gis.fema_flood_zones where area_id=%s", (area_id,)
            ).fetchone()["cnt"]
            if existing > 0:
                print(f"Removing {existing} existing FEMA records for area_id={area_id} (reload)")
                conn.execute("delete from gis.fema_flood_zones where area_id=%s", (area_id,))

            batch_size = 500
            for i in range(0, len(parsed), batch_size):
                batch = parsed[i : i + batch_size]
                for rec in batch:
                    try:
                        # Try to repair invalid geometry via ST_Buffer(0)
                        conn.execute(
                            """insert into gis.fema_flood_zones(
                                area_id, fema_dfirm_id, fld_zone, sfha_tf,
                                zone_subtype, source_feature_id, geom
                            ) values (%s,%s,%s,%s,%s,%s,
                                st_multi(
                                    st_buffer(
                                        st_geomfromtext(%s, 4326),
                                        0
                                    )
                                )
                            )""",
                            (
                                area_id,
                                rec["dfirm_id"],
                                rec["fld_zone"],
                                rec["sfha_tf"],
                                rec["zone_subtype"],
                                rec["source_id"],
                                rec["wkt"],
                            ),
                        )
                        counts["inserted"] += 1
                    except Exception as row_exc:
                        counts["skipped"] += 1
                        print(f"  Skipped feature source_id={rec['source_id']}: {row_exc}")

            print(
                f"FEMA: {counts['inserted']} inserted, {counts['skipped']} skipped\n"
                "REMINDER: These are regulatory hazard zones, not current inundation."
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


def _geojson_to_wkt(gtype: str, coords: list) -> str:
    if gtype == "Polygon":
        rings = ",".join("(" + ",".join(f"{x} {y}" for x, y in ring) + ")" for ring in coords)
        return f"POLYGON({rings})"
    elif gtype == "MultiPolygon":
        polys = []
        for poly_coords in coords:
            rings = ",".join(
                "(" + ",".join(f"{x} {y}" for x, y in ring) + ")"
                for ring in poly_coords
            )
            polys.append(f"({rings})")
        return "MULTIPOLYGON(" + ",".join(polys) + ")"
    raise ValueError(f"Unsupported geometry type: {gtype}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--area-id", type=int, required=True)
    p.add_argument(
        "--fema-geojson",
        default="data/raw/fema_nfhl/fema_nfhl_flood_hazard_zones.geojson",
    )
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    load_fema(
        area_id=args.area_id,
        fema_path=args.fema_geojson,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
