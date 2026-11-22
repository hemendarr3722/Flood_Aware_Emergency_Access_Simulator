import json
from fastapi import HTTPException
from backend.app.core.database import db


def build_ordered_linestring(edge_rows: list[dict]) -> dict | None:
    """
    Assemble an ordered GeoJSON LineString from sequential edge geometries.
    Ensures head-to-tail coordinate continuity without duplicate adjacent vertices.
    """
    if not edge_rows:
        return None

    coords: list[list[float]] = []
    for row in edge_rows:
        raw_geom = row.get("geometry")
        if not raw_geom:
            continue
        geom = json.loads(raw_geom) if isinstance(raw_geom, str) else raw_geom
        edge_coords = geom.get("coordinates", [])
        if not edge_coords:
            continue

        if not coords:
            coords.extend(edge_coords)
        else:
            prev_pt = coords[-1]
            first_pt = edge_coords[0]
            last_pt = edge_coords[-1]

            dist_normal = (first_pt[0] - prev_pt[0]) ** 2 + (first_pt[1] - prev_pt[1]) ** 2
            dist_rev = (last_pt[0] - prev_pt[0]) ** 2 + (last_pt[1] - prev_pt[1]) ** 2

            if dist_rev < dist_normal:
                edge_coords = list(reversed(edge_coords))

            coords.extend(edge_coords[1:])

    if len(coords) < 2:
        return None
    return {"type": "LineString", "coordinates": coords}


def execute_point_to_point_route(
    origin_node_id: int,
    destination_node_id: int,
    scenario_id: int | None = None,
) -> dict:
    if origin_node_id == destination_node_id:
        return {
            "reachable": True,
            "travel_time_s": 0.0,
            "edge_count": 0,
            "edges": [],
            "geometry": None,
            "facility": None,
            "algorithm_version": "pgr_dijkstra_1.0",
        }

    with db() as conn:
        rows = conn.execute(
            """
            select
                d.seq, d.path_seq, d.node, d.edge, d.cost, d.agg_cost,
                e.id as edge_id, e.source, e.target, e.length_m, e.cost_s,
                e.highway_class, st_asgeojson(e.geom) as geometry
            from gis.route_edges(%s, %s, %s) d
            left join gis.road_edges e on e.id = d.edge
            order by d.path_seq asc
            """,
            (origin_node_id, destination_node_id, scenario_id),
        ).fetchall()

    edges = [r for r in rows if r["edge"] >= 0]
    if not edges:
        return {
            "reachable": False,
            "travel_time_s": None,
            "edge_count": 0,
            "edges": [],
            "geometry": None,
            "facility": None,
            "algorithm_version": "pgr_dijkstra_1.0",
        }

    total_time_s = sum(r["cost"] for r in edges)
    linestring = build_ordered_linestring(edges)

    return {
        "reachable": True,
        "travel_time_s": round(total_time_s, 2),
        "edge_count": len(edges),
        "edges": [
            {
                "edge_id": e["edge_id"],
                "source": e["source"],
                "target": e["target"],
                "length_m": float(e["length_m"]) if e["length_m"] is not None else 0.0,
                "cost_s": float(e["cost_s"]) if e["cost_s"] is not None else 0.0,
                "highway": e["highway_class"],
            }
            for e in edges
        ],
        "geometry": linestring,
        "facility": None,
        "algorithm_version": "pgr_dijkstra_1.0",
    }


def execute_nearest_facility_route(
    origin_node_id: int,
    facility_type: str,
    scenario_id: int | None = None,
) -> dict:
    with db() as conn:
        fac_rows = conn.execute(
            "select * from gis.route_nearest_facility(%s, %s, %s)",
            (origin_node_id, facility_type, scenario_id),
        ).fetchall()

        if not fac_rows:
            return {
                "reachable": False,
                "travel_time_s": None,
                "facility": None,
                "edge_count": 0,
                "edges": [],
                "geometry": None,
                "algorithm_version": "pgr_dijkstra_1.0",
            }

        fac = fac_rows[0]
        path_edges = fac.get("path_edges") or []

        if not path_edges:
            # Origin is already at facility
            return {
                "reachable": True,
                "travel_time_s": 0.0,
                "facility": {
                    "id": fac["facility_id"],
                    "name": fac["facility_name"],
                    "type": fac["facility_type"],
                    "node_id": fac["facility_node_id"],
                },
                "edge_count": 0,
                "edges": [],
                "geometry": None,
                "algorithm_version": "pgr_dijkstra_1.0",
            }

        edge_details = conn.execute(
            """
            select
                e.id as edge_id, e.source, e.target, e.length_m, e.cost_s,
                e.highway_class, st_asgeojson(e.geom) as geometry,
                idx.ord
            from unnest(%s::bigint[]) with ordinality as idx(edge_id, ord)
            join gis.road_edges e on e.id = idx.edge_id
            order by idx.ord asc
            """,
            (path_edges,),
        ).fetchall()

    linestring = build_ordered_linestring(edge_details)

    return {
        "reachable": True,
        "travel_time_s": round(fac["total_travel_time_s"], 2),
        "facility": {
            "id": fac["facility_id"],
            "name": fac["facility_name"],
            "type": fac["facility_type"],
            "node_id": fac["facility_node_id"],
        },
        "edge_count": fac["edge_count"],
        "edges": [
            {
                "edge_id": e["edge_id"],
                "source": e["source"],
                "target": e["target"],
                "length_m": float(e["length_m"]) if e["length_m"] is not None else 0.0,
                "cost_s": float(e["cost_s"]) if e["cost_s"] is not None else 0.0,
                "highway": e["highway_class"],
            }
            for e in edge_details
        ],
        "geometry": linestring,
        "algorithm_version": "pgr_dijkstra_1.0",
    }


def compare_routes(
    origin_node_id: int,
    destination_node_id: int | None = None,
    facility_type: str | None = None,
    scenario_id: int = 2,
) -> dict:
    if destination_node_id is not None:
        base_res = execute_point_to_point_route(origin_node_id, destination_node_id, scenario_id=None)
        flood_res = execute_point_to_point_route(origin_node_id, destination_node_id, scenario_id=scenario_id)
    elif facility_type is not None:
        base_res = execute_nearest_facility_route(origin_node_id, facility_type, scenario_id=None)
        flood_res = execute_nearest_facility_route(origin_node_id, facility_type, scenario_id=scenario_id)
    else:
        raise HTTPException(
            status_code=422,
            detail="Either destination_node_id or facility_type must be specified",
        )

    base_time = base_res.get("travel_time_s")
    flood_time = flood_res.get("travel_time_s")

    delay_s = None
    delay_pct = None
    if base_time is not None and flood_time is not None:
        delay_s = round(flood_time - base_time, 2)
        delay_pct = round((delay_s / base_time) * 100, 1) if base_time > 0 else 0.0

    # Determine status
    if not flood_res.get("reachable"):
        status = "isolated"
    elif delay_s is not None and delay_s > 0.01:
        status = "detoured"
    else:
        status = "unaffected"

    return {
        "status": status,
        "delay_s": delay_s,
        "delay_pct": delay_pct,
        "baseline": base_res,
        "disrupted": flood_res,
        "modeling_disclaimer": "Modeled potentially affected routes. Not verified real-world closures.",
    }
