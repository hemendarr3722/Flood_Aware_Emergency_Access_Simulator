from typing import Literal
from pydantic import BaseModel


class FacilityResponse(BaseModel):
    id: int
    name: str
    facility_type: Literal["hospital", "shelter", "fire_station"]
    is_active: bool
    validation_status: Literal["candidate", "verified", "excluded"]
    exclusion_reason: str | None = None
    snap_distance_m: float | None = None
    road_node_id: int | None = None
    lat: float
    lon: float
