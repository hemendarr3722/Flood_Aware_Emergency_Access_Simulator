from fastapi import APIRouter, Path
from backend.app.repository.study_area_repo import list_study_areas, get_study_area_summary
from backend.app.schemas.study_area import StudyAreaListItem, StudyAreaSummary

router = APIRouter(tags=["Study Areas"])


@router.get(
    "/api/study-areas",
    response_model=list[StudyAreaListItem],
    summary="List registered study areas",
    description="Returns all active geographic study areas configured in the simulator database.",
)
def get_study_areas():
    return list_study_areas()


@router.get(
    "/api/study-areas/{area_id}/summary",
    response_model=StudyAreaSummary,
    summary="Get study area summary metrics",
    description="Returns bounding coordinates, road network counts, facility counts, and population metrics for a study area.",
)
def get_study_area(
    area_id: int = Path(..., ge=1, description="Unique study area ID"),
):
    return get_study_area_summary(area_id)
