from typing import Any, Literal
from pydantic import BaseModel
from backend.app.schemas.common import GeoJSONGeometry


class RouteEdgeItem(BaseModel):
    edge_id: int
    source: int
    target: int
    length_m: float
    cost_s: float
    highway: str | None = None


class FacilityTargetInfo(BaseModel):
    id: int
    name: str
    type: str
    node_id: int


class RouteResponse(BaseModel):
    reachable: bool
    travel_time_s: float | None = None
    edge_count: int = 0
    edges: list[RouteEdgeItem] = []
    geometry: GeoJSONGeometry | None = None
    facility: FacilityTargetInfo | None = None
    algorithm_version: str = "pgr_dijkstra_1.0"


class CompareRouteResponse(BaseModel):
    status: Literal["unaffected", "detoured", "isolated"]
    delay_s: float | None = None
    delay_pct: float | None = None
    baseline: RouteResponse
    disrupted: RouteResponse
    modeling_disclaimer: str
