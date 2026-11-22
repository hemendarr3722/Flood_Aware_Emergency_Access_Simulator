"""Inventory or download USGS 3DEP elevation products for a WGS84 bbox.

Important: a DEM represents terrain elevation. It is not a flood-depth raster.
Use it only as terrain context or as an input to a separately validated model.
"""

from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path

from common import bbox_text, download_file, parse_bbox, request_json, utc_now, write_json


PRODUCTS_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
DEFAULT_DATASET = "Digital Elevation Model (DEM) 1 meter"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", default="-95.45,29.68,-95.25,29.85")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path("data/raw/usgs_3dep"))
    parser.add_argument("--download", action="store_true", help="Download files after saving the inventory.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum products to download; 0 means all matches.")
    parser.add_argument(
        "--title-contains",
        help="Download only products whose catalog title contains this text (case-insensitive).",
    )
    parser.add_argument("--max-file-gb", type=float, default=5.0)
    parser.add_argument("--download-timeout", type=int, default=900)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def product_inventory(bbox: tuple[float, float, float, float], dataset: str) -> dict:
    items: list[dict] = []
    offset = 0
    total = None
    while total is None or offset < total:
        page = request_json(
            PRODUCTS_API,
            {
                "bbox": bbox_text(bbox),
                "datasets": dataset,
                "outputFormat": "JSON",
                "max": 100,
                "offset": offset,
            },
        )
        total = int(page.get("total", 0))
        batch = page.get("items", [])
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
    return {"total": int(total or 0), "items": items}


def destination_name(item: dict, index: int) -> str:
    url = str(item.get("downloadURL") or "")
    name = Path(urllib.parse.urlparse(url).path).name
    return name or f"usgs_3dep_product_{index:04d}.bin"


def main() -> None:
    args = parse_args()
    bbox = parse_bbox(args.bbox)
    if args.limit < 0 or args.max_file_gb <= 0 or args.download_timeout <= 0:
        raise SystemExit("Download limits must be non-negative/positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    catalog = product_inventory(bbox, args.dataset)
    unique: dict[str, dict] = {}
    for item in catalog["items"]:
        url = item.get("downloadURL")
        if isinstance(url, str) and url.startswith("https://"):
            unique[url] = item
    items = list(unique.values())
    selected_items = items
    if args.title_contains:
        needle = args.title_contains.casefold()
        selected_items = [
            item for item in items if needle in str(item.get("title") or "").casefold()
        ]
        if args.download and not selected_items:
            raise SystemExit(f"No products matched --title-contains={args.title_contains!r}")

    downloads: list[dict] = []
    if args.download:
        selected = selected_items[: args.limit] if args.limit else selected_items
        for index, item in enumerate(selected, start=1):
            url = item["downloadURL"]
            downloads.append(
                download_file(
                    url,
                    output / "products" / destination_name(item, index),
                    overwrite=args.overwrite,
                    max_bytes=int(args.max_file_gb * 1024**3),
                    timeout=args.download_timeout,
                )
            )

    write_json(
        output / "inventory.json",
        {
            "queried_at": utc_now(),
            "publisher": "U.S. Geological Survey",
            "dataset": args.dataset,
            "products_api": PRODUCTS_API,
            "bbox_wgs84": bbox,
            "api_total": catalog["total"],
            "unique_download_count": len(items),
            "selection": {
                "title_contains": args.title_contains,
                "matching_product_count": len(selected_items),
                "download_limit": args.limit,
            },
            "items": items,
            "downloads": downloads,
            "modeling_warning": "3DEP elevation is terrain elevation, not flood depth and not a road-closure observation.",
        },
    )
    print(f"Found {len(items)} USGS 3DEP products; downloaded {len(downloads)}")


if __name__ == "__main__":
    main()

