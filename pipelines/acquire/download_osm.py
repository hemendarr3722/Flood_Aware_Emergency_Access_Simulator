"""Download a reproducible OSMnx snapshot of roads, facilities, and boundary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


FACILITY_TAGS = {
    "amenity": ["hospital", "clinic", "fire_station", "police"],
    "emergency": "shelter",
    "social_facility": "shelter",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--place", default="Downtown, Houston, Harris County, Texas, United States")
    parser.add_argument("--network-type", default="drive")
    parser.add_argument("--output", type=Path, default=Path("data/raw/osm"))
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    try:
        import osmnx as ox
    except ImportError as exc:
        raise SystemExit("OSMnx is required. Run: pip install -r requirements.txt") from exc
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    graph = ox.graph.graph_from_place(
        args.place,
        network_type=args.network_type,
        simplify=True,
        retain_all=False,
    )
    graph = ox.routing.add_edge_speeds(graph)
    graph = ox.routing.add_edge_travel_times(graph)
    nodes, edges = ox.convert.graph_to_gdfs(graph, nodes=True, edges=True)
    boundary = ox.geocoder.geocode_to_gdf(args.place).to_crs(4326)
    facilities = ox.features.features_from_place(args.place, FACILITY_TAGS).to_crs(4326)

    ox.io.save_graphml(graph, output / "drive_network.graphml")
    write_text(output / "road_nodes.geojson", nodes.to_crs(4326).reset_index().to_json())
    write_text(output / "road_edges.geojson", edges.to_crs(4326).reset_index().to_json())
    write_text(output / "facilities.geojson", facilities.reset_index().to_json())
    write_text(output / "study_area.geojson", boundary.to_json())
    (output / "metadata.json").write_text(
        json.dumps(
            {
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "source": "OpenStreetMap via OSMnx/Nominatim/Overpass",
                "place_query": args.place,
                "network_type": args.network_type,
                "osmnx_version": ox.__version__,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "facility_feature_count": len(facilities),
                "validation_warning": "OSM facility tags do not prove current emergency or shelter operations.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(nodes)} nodes, {len(edges)} edges, and {len(facilities)} facility features")


if __name__ == "__main__":
    main()
