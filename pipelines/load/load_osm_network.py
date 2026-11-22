"""
load_osm_network.py — Idempotent loader for road nodes and edges.

Reads already-downloaded raw OSM GeoJSON files (from pipelines/acquire/download_osm.py).
Does NOT make network requests. Requires a migrated database.

Speed assignment uses documented highway-class defaults when OSM maxspeed is absent.
All costs are stored in seconds (travel time), lengths in metres.
One-way streets: each directed arc is stored separately; reverse_cost_s = -1.

Usage:
    python pipelines/load/load_osm_network.py \\
        --area-id 1 \\
        --nodes data/raw/osm/road_nodes.geojson \\
        --edges data/raw/osm/road_edges.geojson \\
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

# Default speed table (km/h) sourced from OSMnx defaults and OpenStreetMap wiki.
# Reference: https://wiki.openstreetmap.org/wiki/Key:maxspeed
HIGHWAY_SPEED_DEFAULTS: dict[str, float] = {
    "motorway": 97.0,
    "motorway_link": 72.0,
    "trunk": 88.0,
    "trunk_link": 56.0,
    "primary": 72.0,
    "primary_link": 56.0,
    "secondary": 56.0,
    "secondary_link": 48.0,
    "tertiary": 48.0,
    "tertiary_link": 40.0,
    "unclassified": 40.0,
    "residential": 32.0,
    "living_street": 16.0,
    "service": 24.0,
    "road": 40.0,
}
FALLBACK_SPEED_KMH = 32.0  # explicitly named, not silently applied


def _resolve_speed(props: dict) -> tuple[float, str]:
    """Return (speed_kmh, source) where source is 'tagged'|'highway_default'|'fallback'."""
    raw_speed = props.get("speed_kph") or props.get("speed_kmh")
    if raw_speed is not None:
        try:
            return float(raw_speed), "tagged"
        except (TypeError, ValueError):
            pass
    hw = props.get("highway", "")
    if isinstance(hw, list):
        hw = hw[0] if hw else ""
    if hw in HIGHWAY_SPEED_DEFAULTS:
        return HIGHWAY_SPEED_DEFAULTS[hw], "highway_default"
    return FALLBACK_SPEED_KMH, "fallback"


def _travel_time_s(length_m: float, speed_kmh: float) -> float:
    """Return travel time in seconds. Speed must be > 0."""
    if speed_kmh <= 0:
        raise ValueError(f"speed_kmh must be positive, got {speed_kmh}")
    return length_m / (speed_kmh / 3.6)


def load_network(
    area_id: int,
    nodes_path: str,
    edges_path: str,
    dsn: str,
    dry_run: bool,
) -> dict:
    with open(nodes_path) as f:
        nodes_fc = json.load(f)
    with open(edges_path) as f:
        edges_fc = json.load(f)

    node_features = nodes_fc.get("features", [])
    edge_features = edges_fc.get("features", [])
    print(f"Input: {len(node_features)} nodes, {len(edge_features)} directed edge arcs")

    # Validate: check every edge has non-null length, speed derivable
    missing_length = sum(
        1 for f in edge_features
        if f.get("properties", {}).get("length") is None
    )
    if missing_length:
        print(f"WARNING: {missing_length} edges have null length — will be skipped")

    # Collect node IDs present in edges to detect disconnected nodes
    edge_node_ids: set[int] = set()
    for feat in edge_features:
        props = feat.get("properties", {})
        if props.get("from") and props.get("to"):
            edge_node_ids.add(int(props["from"]))
            edge_node_ids.add(int(props["to"]))

    if dry_run:
        print("DRY RUN — no database changes. Pass --confirm-write to load.")
        return {"nodes": len(node_features), "edges": len(edge_features)}

    counts = {"nodes_inserted": 0, "nodes_skipped": 0,
              "edges_inserted": 0, "edges_skipped": 0,
              "speed_tagged": 0, "speed_hw_default": 0, "speed_fallback": 0}

    from psycopg import connect
    from psycopg.rows import dict_row
    with connect(dsn, row_factory=dict_row) as conn:
        conn.execute(
            "insert into gis.processing_runs(pipeline, area_id, status) values(%s,%s,'running')",
            ("load_osm_network", area_id),
        )
        run_id = conn.execute(
            "select id from gis.processing_runs where pipeline=%s order by id desc limit 1",
            ("load_osm_network",),
        ).fetchone()["id"]

        try:
            # ── Nodes (idempotent: ON CONFLICT DO NOTHING) ───────────────────
            existing_nodes = {
                r["id"]
                for r in conn.execute(
                    "select id from gis.road_nodes where area_id=%s", (area_id,)
                ).fetchall()
            }

            node_rows = []
            for feat in node_features:
                props = feat.get("properties", {})
                node_id = int(props.get("osmid") or props.get("id"))
                geom = feat.get("geometry", {})
                if geom.get("type") != "Point":
                    continue
                x, y = geom["coordinates"]
                if node_id not in existing_nodes:
                    node_rows.append((node_id, area_id, float(x), float(y)))

            if node_rows:
                with conn.cursor().copy(
                    "copy gis.road_nodes(id,area_id,geom) from stdin"
                ) as cp:
                    for nid, aid, x, y in node_rows:
                        cp.write_row((nid, aid, f"SRID=4326;POINT({x} {y})"))
            counts["nodes_inserted"] = len(node_rows)
            counts["nodes_skipped"] = len(node_features) - len(node_rows)
            print(f"Nodes: {counts['nodes_inserted']} inserted, {counts['nodes_skipped']} already existed")

            # ── Edges (idempotent: skip if osm_way_id+source+target exists) ─
            existing_edges: set[tuple] = {
                (r["osm_way_id"], r["source"], r["target"])
                for r in conn.execute(
                    "select osm_way_id, source, target from gis.road_edges where area_id=%s",
                    (area_id,),
                ).fetchall()
            }

            edge_rows = []
            for feat in edge_features:
                props = feat.get("properties", {})
                length_m = props.get("length")
                if length_m is None:
                    counts["edges_skipped"] += 1
                    continue
                length_m = float(length_m)
                u = int(props.get("from") or props.get("u"))
                v = int(props.get("to") or props.get("v"))
                osm_way_id = str(props.get("osmid") or props.get("osm_way_id") or "")
                highway = props.get("highway", "")
                if isinstance(highway, list):
                    highway = highway[0] if highway else ""

                # Speed and travel time
                speed_kmh, speed_src = _resolve_speed(props)
                cost_s = _travel_time_s(length_m, speed_kmh)
                # Stored as one-way directed arc (reverse forbidden)
                reverse_cost_s = -1.0

                # Bridge / tunnel / layer
                is_bridge = str(props.get("bridge", "")).lower() in ("yes", "true", "1")
                is_tunnel = str(props.get("tunnel", "")).lower() in ("yes", "true", "1")
                try:
                    layer_tag = int(props.get("layer", 0))
                except (TypeError, ValueError):
                    layer_tag = 0

                geom = feat.get("geometry", {})
                if geom.get("type") != "LineString":
                    counts["edges_skipped"] += 1
                    continue
                coords = geom["coordinates"]
                wkt_coords = ",".join(f"{x} {y}" for x, y in coords)
                wkt = f"SRID=4326;LINESTRING({wkt_coords})"

                key = (osm_way_id, u, v)
                if key in existing_edges:
                    counts["edges_skipped"] += 1
                    continue

                edge_rows.append((
                    area_id, osm_way_id, u, v,
                    length_m, speed_kmh, cost_s, reverse_cost_s,
                    highway, is_bridge, is_tunnel, layer_tag, speed_src,
                    wkt,
                ))
                counts[f"speed_{speed_src.replace('-','_')}"] = \
                    counts.get(f"speed_{speed_src}", 0) + 1

            if edge_rows:
                with conn.cursor().copy(
                    "copy gis.road_edges("
                    "area_id,osm_way_id,source,target,"
                    "length_m,speed_kmh,cost_s,reverse_cost_s,"
                    "highway_class,is_bridge,is_tunnel,layer_tag,osm_speed_source,"
                    "geom) from stdin"
                ) as cp:
                    for row in edge_rows:
                        cp.write_row(row[:-1] + (row[-1],))

            counts["edges_inserted"] = len(edge_rows)
            print(
                f"Edges: {counts['edges_inserted']} inserted, {counts['edges_skipped']} skipped\n"
                f"Speed sources: tagged={counts['speed_tagged']}, "
                f"hw_default={counts['speed_hw_default']}, "
                f"fallback={counts['speed_fallback']}"
            )

            # Validation: spot check cost > 0
            bad = conn.execute(
                "select count(*) cnt from gis.road_edges where area_id=%s and cost_s<=0",
                (area_id,),
            ).fetchone()["cnt"]
            if bad:
                raise RuntimeError(f"Validation failed: {bad} edges with cost_s<=0")

            conn.execute(
                "update gis.processing_runs set status='success', finished_at=now(), "
                "row_counts=%s where id=%s",
                (json.dumps(counts), run_id),
            )
            conn.commit()
            print("Network loaded and validated.")

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
    p.add_argument("--nodes", default="data/raw/osm/road_nodes.geojson")
    p.add_argument("--edges", default="data/raw/osm/road_edges.geojson")
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    load_network(
        area_id=args.area_id,
        nodes_path=args.nodes,
        edges_path=args.edges,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
