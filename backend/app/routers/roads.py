from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from backend.app.core.config import settings
from backend.app.repository.road_repo import get_roads
from backend.app.schemas.common import GeoJSONFeatureCollection

router = APIRouter(tags=["Roads"])


def parse_and_validate_bbox(bbox_str: str, max_span: float) -> tuple[float, float, float, float]:
    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422,
            detail="bbox must contain exactly 4 comma-separated values: min_lon,min_lat,max_lon,max_lat",
        )
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p.strip()) for p in parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox coordinates must be valid numeric floats")

    if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        raise HTTPException(status_code=422, detail="Longitudes must be within range [-180, 180]")
    if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
        raise HTTPException(status_code=422, detail="Latitudes must be within range [-90, 90]")
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(
            status_code=422,
            detail="Invalid bbox: min values must be strictly less than max values (min_lon < max_lon and min_lat < max_lat)",
        )
    if (max_lon - min_lon) > max_span or (max_lat - min_lat) > max_span:
        raise HTTPException(
            status_code=422,
            detail=f"Bounding box exceeds maximum allowed span of {max_span} degrees (~55 km)",
        )
    return min_lon, min_lat, max_lon, max_lat


@router.get(
    "/api/roads",
    response_model=GeoJSONFeatureCollection,
    summary="Get road network edges as GeoJSON",
    description="Returns drivable road network edges within an optional bounding box or scenario state filter.",
)
def get_road_edges(
    area_id: int = Query(..., ge=1, description="Study area ID"),
    bbox: str | None = Query(
        default=None,
        description="Optional bounding box formatted as min_lon,min_lat,max_lon,max_lat (max span 0.5 degrees)",
    ),
    scenario_id: int | None = Query(
        default=None,
        ge=1,
        description="Optional scenario ID to evaluate edge closure state against",
    ),
    state: Literal["all", "normal", "closed", "affected"] = Query(
        default="all",
        description="Filter by edge condition: 'all', 'normal' (passable), or 'closed'/'affected'",
    ),
    limit: int = Query(
        default=1000,
        ge=1,
        le=3000,
        description="Maximum features returned (capped at 3000)",
    ),
):
    bbox_coords = None
    if bbox:
        bbox_coords = parse_and_validate_bbox(bbox, max_span=settings.MAX_BBOX_SPAN_DEG)

    return get_roads(
        area_id=area_id,
        bbox_coords=bbox_coords,
        scenario_id=scenario_id,
        state=state,
        limit=limit,
    )
