from fastapi import APIRouter, Path, Query
from backend.app.repository.scenario_repo import (
    list_scenarios,
    get_scenario,
    get_affected_roads,
    get_closed_roads,
    get_scenario_impact,
    get_accessibility_origins,
)
from backend.app.schemas.common import GeoJSONFeatureCollection
from backend.app.schemas.scenario import (
    ScenarioListItem,
    ScenarioDetail,
    ScenarioImpactResponse,
)

router = APIRouter(tags=["Scenarios"])


@router.get(
    "/api/scenarios",
    response_model=list[ScenarioListItem],
    summary="List flood and baseline scenarios",
    description="Returns all registered baseline and flood hazard scenarios for a study area.",
)
def get_scenarios(
    area_id: int = Query(..., ge=1, description="Study area ID"),
):
    return list_scenarios(area_id)


@router.get(
    "/api/scenarios/{scenario_id}",
    response_model=ScenarioDetail,
    summary="Get scenario details and impact counts",
    description="Returns scenario metadata, modeling rule, disclaimer, and count of affected road edges.",
)
def get_scenario_by_id(
    scenario_id: int = Path(..., ge=1, description="Scenario ID"),
):
    return get_scenario(scenario_id)


@router.get(
    "/api/scenarios/{scenario_id}/affected-roads",
    summary="Get affected road edges as GeoJSON",
    description="Returns road edges modeled as potentially affected in the scenario with flood zone attributes.",
)
def get_scenario_affected_roads(
    scenario_id: int = Path(..., ge=1, description="Scenario ID"),
    limit: int = Query(default=3000, ge=1, le=5000),
):
    return get_affected_roads(scenario_id, limit=limit)


@router.get(
    "/api/scenarios/{scenario_id}/closed-roads",
    summary="Get closed road edges as GeoJSON (legacy endpoint)",
    description="Returns closed road edges for backward compatibility with frontend layer loaders.",
)
def get_scenario_closed_roads(
    scenario_id: int = Path(..., ge=1, description="Scenario ID"),
    limit: int = Query(default=3000, ge=1, le=5000),
):
    return get_closed_roads(scenario_id, limit=limit)


@router.get(
    "/api/scenarios/{scenario_id}/impact",
    response_model=ScenarioImpactResponse,
    summary="Get aggregate population accessibility impact",
    description=(
        "Returns modeled population within and beyond the travel-time threshold, unreachable population, "
        "population losing threshold access compared to baseline, and reconciliation checks."
    ),
)
def get_impact_metrics(
    scenario_id: int = Path(..., ge=1, description="Scenario ID"),
    threshold_minutes: int = Query(
        default=15,
        ge=5,
        le=120,
        description="Accessibility travel time threshold in minutes",
    ),
):
    return get_scenario_impact(scenario_id, threshold_minutes=threshold_minutes)


@router.get(
    "/api/scenarios/{scenario_id}/accessibility-origins",
    summary="Get population origins and accessibility status as GeoJSON",
    description="Returns Census block-group representative origins with travel time, nearest facility, and reachability status.",
)
def get_origins_geojson(
    scenario_id: int = Path(..., ge=1, description="Scenario ID"),
    threshold_minutes: int = Query(
        default=15,
        ge=5,
        le=120,
        description="Accessibility travel time threshold in minutes",
    ),
):
    return get_accessibility_origins(scenario_id, threshold_minutes=threshold_minutes)
