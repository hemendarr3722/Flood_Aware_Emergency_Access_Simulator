import json
from fastapi import HTTPException
from backend.app.core.database import fetch_all, fetch_one


def list_scenarios(area_id: int):
    return fetch_all(
        """select id, name, description, scenario_kind, threshold_m, status
           from gis.flood_scenarios where area_id = %s order by id""",
        (area_id,),
    )


def get_scenario(scenario_id: int):
    rows = fetch_all(
        """select id, area_id, name, description, scenario_kind, threshold_m,
           status, algorithm_version, created_at
           from gis.flood_scenarios where id = %s""",
        (scenario_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    sc = rows[0]

    impact_stats = fetch_all(
        """select count(*) as affected_road_count,
           coalesce(round(avg(intersection_fraction)::numeric, 3), 0) as avg_intersection_fraction
           from gis.scenario_edge_impacts
           where scenario_id = %s and is_closed = true""",
        (scenario_id,),
    )[0]

    rule = (
        "Normal baseline conditions without flood hazard or road closures."
        if sc["scenario_kind"] == "baseline"
        else "Road edges intersecting FEMA NFHL Special Flood Hazard Area (1% annual-chance / 100-year) "
        "zones are modeled as potentially affected and excluded from emergency routes in this planning scenario."
    )
    disclaimer = (
        "Planning simulation only. Modeled potentially affected roads represent regulatory "
        "flood hazard zones from FEMA NFHL, NOT verified real-world inundation or water depth. "
        "Never use for live emergency navigation."
    )

    return {
        **sc,
        "affected_road_count": impact_stats["affected_road_count"],
        "avg_intersection_fraction": float(impact_stats["avg_intersection_fraction"]),
        "modeling_rule": rule,
        "disclaimer": disclaimer,
    }


def get_affected_roads(scenario_id: int, limit: int = 3000):
    # Verify scenario exists
    sc = fetch_one("select id from gis.flood_scenarios where id = %s", (scenario_id,))
    if not sc:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    rows = fetch_all(
        """select e.id, i.depth_m, i.flood_zone, i.sfha_tf, i.intersection_fraction,
           i.impact_kind, e.highway_class, e.length_m,
           st_asgeojson(e.geom) as geometry
           from gis.scenario_edge_impacts i
           join gis.road_edges e on e.id = i.edge_id
           where i.scenario_id = %s and i.is_closed
           order by e.id limit %s""",
        (scenario_id, limit),
    )
    return {
        "type": "FeatureCollection",
        "scenario_id": scenario_id,
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "edge_id": r["id"],
                    "impact_kind": r["impact_kind"],
                    "flood_zone": r["flood_zone"],
                    "sfha_tf": r["sfha_tf"],
                    "intersection_fraction": float(r["intersection_fraction"])
                    if r["intersection_fraction"] is not None
                    else None,
                    "length_m": float(r["length_m"]) if r["length_m"] is not None else None,
                    "highway": r["highway_class"],
                },
                "geometry": json.loads(r["geometry"])
                if isinstance(r["geometry"], str)
                else r["geometry"],
            }
            for r in rows
        ],
    }


def get_closed_roads(scenario_id: int, limit: int = 3000):
    sc = fetch_one("select id from gis.flood_scenarios where id = %s", (scenario_id,))
    if not sc:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    rows = fetch_all(
        """select e.id, i.depth_m, i.flood_zone, st_asgeojson(e.geom) as geometry
           from gis.scenario_edge_impacts i
           join gis.road_edges e on e.id = i.edge_id
           where i.scenario_id = %s and i.is_closed limit %s""",
        (scenario_id, limit),
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": r["id"],
                    "depth_m": float(r["depth_m"]) if r["depth_m"] is not None else None,
                    "flood_zone": r["flood_zone"],
                },
                "geometry": json.loads(r["geometry"])
                if isinstance(r["geometry"], str)
                else r["geometry"],
            }
            for r in rows
        ],
    }


def get_scenario_impact(scenario_id: int, threshold_minutes: int = 15):
    threshold_s = threshold_minutes * 60

    rows = fetch_all(
        """
        select
            count(*) as total_origins,
            coalesce(sum(population), 0) as total_population,
            count(*) filter (where reachable) as reachable_origins,
            coalesce(sum(population) filter (where reachable), 0) as reachable_population,
            coalesce(sum(population) filter (where reachable and travel_time_s <= %s), 0) as within_threshold_population,
            coalesce(sum(population) filter (where reachable and travel_time_s > %s), 0) as beyond_threshold_population,
            count(*) filter (where status_category = 'network_unreachable') as network_unreachable_origins,
            coalesce(sum(population) filter (where status_category = 'network_unreachable'), 0) as network_unreachable_population,
            count(*) filter (where status_category = 'invalid_snap') as invalid_snap_origins,
            coalesce(sum(population) filter (where status_category = 'invalid_snap'), 0) as invalid_snap_population,
            round(percentile_cont(0.5) within group (order by travel_time_s)::numeric, 1) as median_travel_time_s,
            round(percentile_cont(0.9) within group (order by travel_time_s)::numeric, 1) as p90_travel_time_s
        from gis.scenario_accessibility
        where scenario_id = %s
        """,
        (threshold_s, threshold_s, scenario_id),
    )

    if not rows or rows[0]["total_origins"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No accessibility data found for scenario {scenario_id}",
        )

    r = rows[0]

    # Calculate baseline comparison (population losing threshold access)
    base_id_row = fetch_all(
        "select id from gis.flood_scenarios where scenario_kind = 'baseline' and area_id = ("
        "  select area_id from gis.flood_scenarios where id = %s"
        ") limit 1",
        (scenario_id,),
    )
    pop_losing_access = 0
    if base_id_row and base_id_row[0]["id"] != scenario_id:
        base_within = fetch_all(
            """select coalesce(sum(population) filter (where reachable and travel_time_s <= %s), 0) as pop
               from gis.scenario_accessibility where scenario_id = %s""",
            (threshold_s, base_id_row[0]["id"]),
        )[0]["pop"]
        pop_losing_access = max(0, base_within - r["within_threshold_population"])

    reconciled_sum = (
        r["within_threshold_population"]
        + r["beyond_threshold_population"]
        + r["network_unreachable_population"]
        + r["invalid_snap_population"]
    )

    return {
        "scenario_id": scenario_id,
        "threshold_minutes": threshold_minutes,
        "total_modeled_population": r["total_population"],
        "total_origins": r["total_origins"],
        "reachable_population": r["reachable_population"],
        "within_threshold_population": r["within_threshold_population"],
        "beyond_threshold_population": r["beyond_threshold_population"],
        "network_unreachable_population": r["network_unreachable_population"],
        "invalid_snap_population": r["invalid_snap_population"],
        "population_losing_threshold_access": pop_losing_access,
        "median_travel_time_s": float(r["median_travel_time_s"])
        if r["median_travel_time_s"] is not None
        else None,
        "p90_travel_time_s": float(r["p90_travel_time_s"])
        if r["p90_travel_time_s"] is not None
        else None,
        "reconciliation": {
            "sum_categories": reconciled_sum,
            "matches_total": reconciled_sum == r["total_population"],
        },
        "modeling_disclaimer": (
            "Planning estimate based on 2024 ACS 5-year block group population using point-on-surface origins. "
            "Not actual real-time population locations or navigation guidance."
        ),
    }


def get_accessibility_origins(scenario_id: int, threshold_minutes: int = 15):
    threshold_s = threshold_minutes * 60
    rows = fetch_all(
        """
        select
            a.origin_id,
            p.geoid,
            a.population,
            a.reachable,
            a.travel_time_s,
            a.status_category,
            a.facility_id,
            f.name as facility_name,
            f.facility_type,
            (a.reachable and a.travel_time_s <= %s) as within_threshold,
            st_asgeojson(p.geom) as geometry
        from gis.scenario_accessibility a
        join gis.population_origins p on p.id = a.origin_id
        left join gis.facilities f on f.id = a.facility_id
        where a.scenario_id = %s
        order by a.origin_id
        """,
        (threshold_s, scenario_id),
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No accessibility origins found for scenario {scenario_id}",
        )

    return {
        "type": "FeatureCollection",
        "scenario_id": scenario_id,
        "threshold_minutes": threshold_minutes,
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "origin_id": r["origin_id"],
                    "geoid": r["geoid"],
                    "population": r["population"],
                    "reachable": r["reachable"],
                    "travel_time_s": r["travel_time_s"],
                    "status_category": r["status_category"],
                    "within_threshold": r["within_threshold"],
                    "facility_name": r.get("facility_name"),
                    "facility_type": r.get("facility_type"),
                },
                "geometry": json.loads(r["geometry"])
                if isinstance(r["geometry"], str)
                else r["geometry"],
            }
            for r in rows
        ],
    }
