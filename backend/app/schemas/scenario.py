from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel


class ScenarioListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    scenario_kind: Literal["baseline", "hazard_polygon", "depth_grid"]
    threshold_m: float | None = None
    status: str


class ScenarioDetail(BaseModel):
    id: int
    area_id: int
    name: str
    description: str | None = None
    scenario_kind: Literal["baseline", "hazard_polygon", "depth_grid"]
    threshold_m: float | None = None
    status: str
    algorithm_version: str | None = None
    created_at: datetime | str | None = None
    affected_road_count: int
    avg_intersection_fraction: float
    modeling_rule: str
    disclaimer: str


class ScenarioImpactReconciliation(BaseModel):
    sum_categories: int
    matches_total: bool


class ScenarioImpactResponse(BaseModel):
    scenario_id: int
    threshold_minutes: int
    total_modeled_population: int
    total_origins: int
    reachable_population: int
    within_threshold_population: int
    beyond_threshold_population: int
    network_unreachable_population: int
    invalid_snap_population: int
    population_losing_threshold_access: int
    median_travel_time_s: float | None = None
    p90_travel_time_s: float | None = None
    reconciliation: ScenarioImpactReconciliation
    modeling_disclaimer: str
