"""Discover public USGS Flood Inundation Mapper sites and linked downloads.

The command saves an inventory even when no site covers the bounding box. It
only downloads URLs explicitly published in site DATA_LINK/REP_LINK fields;
it does not export rendered map images and call them depth rasters.
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from pathlib import Path

from common import bbox_text, download_file, parse_bbox, request_json, utc_now, write_json


SITES_LAYER = "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/sites/MapServer/0"
GRID_SERVICES = {
    "depth_grid_catalog": "https://gis1.wim.usgs.gov/server/rest/services/FIMMapper/grids_tot/MapServer",
    "velocity_grid_catalog": "https://gis2.wim.usgs.gov/arcgis/rest/services/FIMMapper/gridsVelocity/MapServer",
    "water_surface_catalog": "https://gis2.wim.usgs.gov/arcgis/rest/services/FIMMapper/gridsWaterSurface/MapServer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", default="-95.8,29.4,-94.9,30.2")
    parser.add_argument("--output", type=Path, default=Path("data/raw/usgs_fim"))
    parser.add_argument("--download-links", action="store_true")
    parser.add_argument("--max-file-mb", type=int, default=500)
    return parser.parse_args()


def safe_name(value: str, fallback: str) -> str:
    name = Path(urllib.parse.urlparse(value).path).name or fallback
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def main() -> None:
    args = parse_args()
    bbox = parse_bbox(args.bbox)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    query = request_json(
        f"{SITES_LAYER}/query",
        {
            "where": "PUBLIC=1",
            "geometry": bbox_text(bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        },
    )
    features = query.get("features", [])
    sites_path = output / "public_fim_sites.geojson"
    write_json(sites_path, {"type": "FeatureCollection", "features": features})

    downloads: list[dict] = []
    if args.download_links:
        for feature in features:
            properties = feature.get("properties", {})
            site_no = str(properties.get("SITE_NO") or properties.get("OBJECTID") or "site")
            for field in ("DATA_LINK", "REP_LINK"):
                url = properties.get(field)
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                destination = output / "linked_files" / safe_name(url, f"{site_no}_{field.lower()}")
                downloads.append(
                    download_file(
                        url,
                        destination,
                        max_bytes=args.max_file_mb * 1024 * 1024,
                    )
                )

    write_json(
        output / "inventory.json",
        {
            "queried_at": utc_now(),
            "publisher": "U.S. Geological Survey",
            "application": "Flood Inundation Mapper",
            "sites_layer": SITES_LAYER,
            "grid_service_catalogs": GRID_SERVICES,
            "bbox_wgs84": bbox,
            "site_count": len(features),
            "sites": [feature.get("properties", {}) for feature in features],
            "downloads": downloads,
            "coverage_warning": "FIM libraries are site-specific. Zero results means the catalog has no public mapped site intersecting this bbox; do not invent a depth raster.",
        },
    )
    print(f"Found {len(features)} public USGS FIM sites; inventory saved to {output}")


if __name__ == "__main__":
    main()
