from datetime import datetime
from pydantic import BaseModel


class StudyAreaListItem(BaseModel):
    id: int
    name: str
    created_at: datetime | str | None = None


class StudyAreaBounds(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class StudyAreaMetrics(BaseModel):
    total_road_nodes: int
    total_road_edges: int
    total_road_length_km: float
    total_facilities: int
    verified_facilities: int
    candidate_facilities: int
    excluded_facilities: int
    total_population_origins: int
    modeled_population: int
    snapped_pilot_population: int
    available_scenarios: int


class StudyAreaSummary(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime | str | None = None
    bounds: StudyAreaBounds | None = None
    metrics: StudyAreaMetrics
    disclaimer: str
