"""Download FEMA NFHL flood-hazard polygons for a WGS84 bounding box.

This retrieves layer 28 (Flood Hazard Zones) from FEMA's public NFHL ArcGIS
service. These polygons describe mapped regulatory hazard, not current water
depth and not confirmed road inundation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import bbox_text, parse_bbox, request_json, sha256_file, utc_now, write_json


SERVICE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
LAYER_ID = 28
QUERY_URL = f"{SERVICE}/{LAYER_ID}/query"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", default="-95.45,29.68,-95.25,29.85")
    parser.add_argument("--output", type=Path, default=Path("data/raw/fema_nfhl"))
    parser.add_argument("--sfha-only", action="store_true", help="Keep FEMA rows with SFHA_TF='T'.")
    parser.add_argument("--page-size", type=int, default=2000)
    parser.add_argument("--max-features", type=int, default=100000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bbox = parse_bbox(args.bbox)
    if not 1 <= args.page_size <= 2000:
        raise SystemExit("--page-size must be between 1 and 2000")

    layer_info = request_json(f"{SERVICE}/{LAYER_ID}", {"f": "pjson"})
    oid_field = next(
        field["name"]
        for field in layer_info["fields"]
        if field["type"] == "esriFieldTypeOID"
    )
    where = "SFHA_TF='T'" if args.sfha_only else "1=1"
    common_params = {
        "where": where,
        "geometry": bbox_text(bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }
    count_response = request_json(
        QUERY_URL,
        {**common_params, "returnCountOnly": "true", "f": "json"},
    )
    expected = int(count_response["count"])
    if expected > args.max_features:
        raise SystemExit(
            f"Query returns {expected} features; narrow the bbox or raise --max-features intentionally."
        )

    features: list[dict] = []
    offset = 0
    while offset < expected:
        page = request_json(
            QUERY_URL,
            {
                **common_params,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "orderByFields": oid_field,
                "resultOffset": offset,
                "resultRecordCount": args.page_size,
                "f": "geojson",
            },
        )
        batch = page.get("features", [])
        if not batch:
            break
        features.extend(batch)
        offset += len(batch)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    geojson_path = output / "fema_nfhl_flood_hazard_zones.geojson"
    write_json(geojson_path, {"type": "FeatureCollection", "features": features})
    write_json(
        output / "metadata.json",
        {
            "downloaded_at": utc_now(),
            "publisher": "Federal Emergency Management Agency",
            "dataset": "National Flood Hazard Layer — Flood Hazard Zones",
            "service": SERVICE,
            "layer_id": LAYER_ID,
            "layer_name": layer_info.get("name"),
            "bbox_wgs84": bbox,
            "where": where,
            "expected_feature_count": expected,
            "downloaded_feature_count": len(features),
            "sha256": sha256_file(geojson_path),
            "modeling_warning": "Regulatory hazard polygons are not current inundation or flood-depth observations.",
        },
    )
    if len(features) != expected:
        raise SystemExit(f"Incomplete FEMA download: expected {expected}, received {len(features)}")
    print(f"Saved {len(features)} FEMA NFHL features to {geojson_path}")


if __name__ == "__main__":
    main()

