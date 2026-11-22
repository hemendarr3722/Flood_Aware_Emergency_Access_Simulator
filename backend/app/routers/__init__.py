from backend.app.routers.health import router as health_router
from backend.app.routers.study_areas import router as study_areas_router
from backend.app.routers.facilities import router as facilities_router
from backend.app.routers.roads import router as roads_router
from backend.app.routers.scenarios import router as scenarios_router
from backend.app.routers.routes import router as routes_router

__all__ = [
    "health_router",
    "study_areas_router",
    "facilities_router",
    "roads_router",
    "scenarios_router",
    "routes_router",
]
