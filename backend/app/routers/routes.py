from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from backend.app.repository.routing_repo import (
    execute_point_to_point_route,
    execute_nearest_facility_route,
    compare_routes,
)
from backend.app.schemas.routing import RouteResponse, CompareRouteResponse

router = APIRouter(tags=["Routing"])


@router.get(
    "/api/routes",
    response_model=RouteResponse,
    summary="Compute shortest path emergency route",
    description=(
        "Computes optimal Dijkstra route either between two road nodes or from an origin node "
        "to the nearest verified emergency response facility. Returns ordered GeoJSON LineString geometry."
    ),
)
def compute_route(
    origin_node_id: int = Query(..., ge=1, description="Origin road network node ID"),
    destination_node_id: int | None = Query(
        default=None,
        ge=1,
        description="Destination road network node ID (for point-to-point routing)",
    ),
    facility_type: Literal["hospital", "shelter", "fire_station"] | None = Query(
        default=None,
        description="Target facility type (for nearest-facility routing)",
    ),
    scenario_id: int | None = Query(
        default=None,
        ge=1,
        description="Scenario ID (omit or pass 1 for baseline normal network)",
    ),
):
    if destination_node_id is None and facility_type is None:
        raise HTTPException(
            status_code=422,
            detail="Either destination_node_id or facility_type must be specified",
        )

    if destination_node_id is not None:
        return execute_point_to_point_route(
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            scenario_id=scenario_id,
        )

    return execute_nearest_facility_route(
        origin_node_id=origin_node_id,
        facility_type=facility_type,  # type: ignore[arg-type]
        scenario_id=scenario_id,
    )


@router.get(
    "/api/compare/routes",
    response_model=CompareRouteResponse,
    summary="Compare baseline vs flood scenario route",
    description=(
        "Evaluates routing difference between normal baseline and flood-disrupted conditions. "
        "Returns detour delay in seconds, percentage change, and status ('unaffected', 'detoured', 'isolated')."
    ),
)
def compare_route_scenarios(
    origin_node_id: int = Query(..., ge=1, description="Origin road network node ID"),
    destination_node_id: int | None = Query(
        default=None,
        ge=1,
        description="Destination road network node ID (for point-to-point comparison)",
    ),
    facility_type: Literal["hospital", "shelter", "fire_station"] | None = Query(
        default=None,
        description="Target facility type (for nearest-facility comparison)",
    ),
    scenario_id: int = Query(
        default=2,
        ge=1,
        description="Disrupted flood scenario ID to compare against baseline",
    ),
):
    return compare_routes(
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        facility_type=facility_type,
        scenario_id=scenario_id,
    )
