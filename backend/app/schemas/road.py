from typing import Literal
from pydantic import BaseModel
from backend.app.schemas.common import GeoJSONFeatureCollection


class RoadFeatureProperties(BaseModel):
    id: int
    highway: str | None = None
    length_m: float | None = None
    speed_kmh: float | None = None
    cost_s: float | None = None
    is_closed: bool = False
    state: Literal["normal", "closed", "affected"] = "normal"
    impact_kind: str | None = None
    flood_zone: str | None = None
