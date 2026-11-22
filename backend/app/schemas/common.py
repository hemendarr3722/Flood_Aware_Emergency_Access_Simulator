from typing import Any, Literal
from pydantic import BaseModel, Field


class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: Any


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: dict[str, Any]
    geometry: GeoJSONGeometry | None


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]


class HealthResponse(BaseModel):
    status: str
    database_configured: bool


class ReadinessResponse(BaseModel):
    status: str
    extensions: list[str]
    tables_present: int
