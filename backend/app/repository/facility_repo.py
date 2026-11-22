from backend.app.core.database import fetch_all


def get_facilities(
    area_id: int,
    facility_type: str | None = None,
    status: str = "all",
    limit: int = 500,
):
    where_parts = ["area_id = %s"]
    params: list = [area_id]

    if facility_type:
        where_parts.append("facility_type = %s")
        params.append(facility_type)

    if status != "all":
        where_parts.append("validation_status = %s")
        params.append(status)

    where_clause = " and ".join(where_parts)
    params.append(limit)

    return fetch_all(
        f"""select id, name, facility_type, is_active, validation_status,
          exclusion_reason, snap_distance_m, road_node_id,
          st_y(geom) as lat, st_x(geom) as lon
          from gis.facilities
          where {where_clause}
          order by name limit %s""",
        tuple(params),
    )
