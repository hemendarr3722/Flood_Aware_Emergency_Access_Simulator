from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.database import db, fetch_all, fetch_one
from backend.app.core.logging import RequestIdMiddleware, logger
from backend.app.repository.routing_repo import build_ordered_linestring as _build_ordered_linestring
from backend.app.routers import (
    health_router,
    study_areas_router,
    facilities_router,
    roads_router,
    scenarios_router,
    routes_router,
)

tags_metadata = [
    {
        "name": "System",
        "description": "Liveness and readiness probes checking PostGIS/pgRouting health.",
    },
    {
        "name": "Study Areas",
        "description": "Geographic analysis extents, bounding boxes, and summary metrics.",
    },
    {
        "name": "Facilities",
        "description": "Emergency facilities (hospitals, fire stations, shelters) with curation status.",
    },
    {
        "name": "Roads",
        "description": "Road network edges with speed limits, travel costs, and spatial filtering.",
    },
    {
        "name": "Scenarios",
        "description": "Baseline and flood hazard scenarios, affected road segments, and population accessibility impacts.",
    },
    {
        "name": "Routing",
        "description": "Dijkstra point-to-point and nearest-facility routing with detour comparison.",
    },
]

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    openapi_tags=tags_metadata,
)

# 1. Request ID and structured request logger middleware
app.add_middleware(RequestIdMiddleware)

# 2. CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# 3. Standardized error envelope handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", None)
    code = "VALIDATION_ERROR" if exc.status_code == 422 else f"HTTP_{exc.status_code}"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {
                "code": code,
                "message": exc.detail,
                "request_id": req_id,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", None)
    errors = exc.errors()
    msg = "; ".join(f"{e.get('loc', [])}: {e.get('msg')}" for e in errors)
    return JSONResponse(
        status_code=422,
        content={
            "detail": msg,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": msg,
                "details": errors,
                "request_id": req_id,
            },
        },
    )


# 4. Mount API routers
app.include_router(health_router)
app.include_router(study_areas_router)
app.include_router(facilities_router)
app.include_router(roads_router)
app.include_router(scenarios_router)
app.include_router(routes_router)

# Re-export key database utilities for backward compatibility
__all__ = ["app", "db", "fetch_all", "fetch_one", "_build_ordered_linestring"]
