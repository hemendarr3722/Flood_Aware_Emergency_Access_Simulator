from fastapi import HTTPException
from backend.app.core.database import fetch_all, fetch_one


def list_study_areas():
    return fetch_all("select id, name, created_at from gis.study_areas order by id")


def get_study_area_summary(area_id: int):
    area = fetch_one(
        """select id, name, created_at,
           st_xmin(boundary) as min_lon, st_ymin(boundary) as min_lat,
           st_xmax(boundary) as max_lon, st_ymax(boundary) as max_lat
           from gis.study_areas where id = %s""",
        (area_id,),
    )
    if not area:
        raise HTTPException(status_code=404, detail=f"Study area {area_id} not found")

    # Road network stats
    road_stats = fetch_one(
        """select
             (select count(*) from gis.road_nodes where area_id = %s) as total_road_nodes,
             (select count(*) from gis.road_edges where area_id = %s) as total_road_edges,
             coalesce((select round((sum(length_m) / 1000.0)::numeric, 2) from gis.road_edges where area_id = %s), 0) as total_road_length_km
        """,
        (area_id, area_id, area_id),
    ) or {}

    # Facility stats
    fac_stats = fetch_one(
        """select
             count(*) as total_facilities,
             count(*) filter (where validation_status = 'verified') as verified_facilities,
             count(*) filter (where validation_status = 'candidate') as candidate_facilities,
             count(*) filter (where validation_status = 'excluded') as excluded_facilities
           from gis.facilities where area_id = %s""",
        (area_id,),
    ) or {}

    # Population stats
    pop_stats = fetch_one(
        """select
             count(*) as total_population_origins,
             coalesce(sum(population), 0) as modeled_population,
             coalesce(sum(population) filter (where snap_distance_m is not null and snap_distance_m <= 500.0), 0) as snapped_pilot_population
           from gis.population_origins where area_id = %s""",
        (area_id,),
    ) or {}

    # Scenario count
    sc_stats = fetch_one(
        "select count(*) as available_scenarios from gis.flood_scenarios where area_id = %s",
        (area_id,),
    ) or {}

    return {
        "id": area["id"],
        "name": area["name"],
        "description": "Houston Downtown Urban Core Emergency Planning Pilot Area",
        "created_at": area["created_at"],
        "bounds": {
            "min_lon": float(area["min_lon"]) if area["min_lon"] is not None else 0.0,
            "min_lat": float(area["min_lat"]) if area["min_lat"] is not None else 0.0,
            "max_lon": float(area["max_lon"]) if area["max_lon"] is not None else 0.0,
            "max_lat": float(area["max_lat"]) if area["max_lat"] is not None else 0.0,
        },
        "metrics": {
            "total_road_nodes": road_stats.get("total_road_nodes", 0),
            "total_road_edges": road_stats.get("total_road_edges", 0),
            "total_road_length_km": float(road_stats.get("total_road_length_km", 0.0)),
            "total_facilities": fac_stats.get("total_facilities", 0),
            "verified_facilities": fac_stats.get("verified_facilities", 0),
            "candidate_facilities": fac_stats.get("candidate_facilities", 0),
            "excluded_facilities": fac_stats.get("excluded_facilities", 0),
            "total_population_origins": pop_stats.get("total_population_origins", 0),
            "modeled_population": pop_stats.get("modeled_population", 0),
            "snapped_pilot_population": pop_stats.get("snapped_pilot_population", 0),
            "available_scenarios": sc_stats.get("available_scenarios", 0),
        },
        "disclaimer": "Planning simulation area. Not for live emergency navigation or tactical dispatch.",
    }
