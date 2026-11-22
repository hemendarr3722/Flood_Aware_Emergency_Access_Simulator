import json
from backend.app.core.database import fetch_all


def get_roads(
    area_id: int,
    bbox_coords: tuple[float, float, float, float] | None = None,
    scenario_id: int | None = None,
    state: str = "all",
    limit: int = 1000,
) -> dict:
    effective_scenario_id = scenario_id if scenario_id is not None else 0

    where_clauses = ["e.area_id = %s"]
    params: list = [effective_scenario_id, area_id]

    if bbox_coords:
        min_lon, min_lat, max_lon, max_lat = bbox_coords
        where_clauses.append("e.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend([min_lon, min_lat, max_lon, max_lat])

    if state in ("closed", "affected"):
        where_clauses.append("i.is_closed = true")
    elif state == "normal":
        where_clauses.append("(i.is_closed is null or i.is_closed = false)")

    params.append(limit)
    where_sql = " and ".join(where_clauses)

    query = f"""
        select
            e.id,
            e.highway_class,
            e.length_m,
            e.speed_kmh,
            e.cost_s,
            coalesce(i.is_closed, false) as is_closed,
            i.impact_kind,
            i.flood_zone,
            st_asgeojson(e.geom) as geometry
        from gis.road_edges e
        left join gis.scenario_edge_impacts i
            on i.edge_id = e.id and i.scenario_id = %s
        where {where_sql}
        order by e.id
        limit %s
    """

    rows = fetch_all(query, tuple(params))

    features = []
    for r in rows:
        geom = json.loads(r["geometry"]) if isinstance(r["geometry"], str) else r["geometry"]
        features.append({
            "type": "Feature",
            "properties": {
                "id": r["id"],
                "highway": r.get("highway_class"),
                "length_m": r.get("length_m"),
                "speed_kmh": r.get("speed_kmh"),
                "cost_s": r.get("cost_s"),
                "is_closed": r["is_closed"],
                "state": "closed" if r["is_closed"] else "normal",
                "impact_kind": r.get("impact_kind"),
                "flood_zone": r.get("flood_zone"),
            },
            "geometry": geom,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }
