from typing import Literal
from fastapi import APIRouter, Query
from backend.app.repository.facility_repo import get_facilities
from backend.app.schemas.facility import FacilityResponse

router = APIRouter(tags=["Facilities"])


@router.get(
    "/api/facilities",
    response_model=list[FacilityResponse],
    summary="List emergency response facilities",
    description="Returns verified, candidate, or excluded emergency facilities (hospitals, fire stations, shelters) with snap distances.",
)
def list_facilities(
    area_id: int = Query(..., ge=1, description="Study area ID"),
    facility_type: Literal["hospital", "shelter", "fire_station"] | None = Query(
        default=None, description="Optional facility type filter"
    ),
    status: Literal["candidate", "verified", "excluded", "all"] = Query(
        default="all", description="Validation status filter"
    ),
):
    return get_facilities(area_id=area_id, facility_type=facility_type, status=status)
