from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from backend.app.core.config import settings
from backend.app.core.database import db
from backend.app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["System"])


def _mask_target(dsn: str | None) -> str | None:
    if not dsn:
        return None
    try:
        p = urlparse(dsn)
        return f"{p.hostname}:{p.port}"
    except Exception:
        return "unparseable"


@router.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Shallow liveness probe",
    description="Returns service liveness status and indicates whether DATABASE_URL is configured.",
)
def health():
    return {
        "status": "ok",
        "database_configured": bool(settings.DATABASE_URL),
        "db_target": _mask_target(settings.DATABASE_URL),
    }


@router.get(
    "/api/readiness",
    response_model=ReadinessResponse,
    summary="Deep readiness probe",
    description="Verifies database connectivity, PostGIS and pgRouting extensions, and minimum schema table count.",
)
def readiness():
    with db() as conn:
        exts = {
            r["extname"]
            for r in conn.execute(
                "select extname from pg_extension where extname in ('postgis','pgrouting')"
            ).fetchall()
        }
        if "postgis" not in exts or "pgrouting" not in exts:
            raise HTTPException(
                status_code=503,
                detail="Required PostGIS/pgRouting extensions not installed in database",
            )
        table_count = conn.execute(
            "select count(*) cnt from information_schema.tables where table_schema='gis'"
        ).fetchone()["cnt"]
        if table_count < 9:
            raise HTTPException(
                status_code=503,
                detail=f"GIS schema incomplete: {table_count} tables present, minimum 9 required",
            )
    return {
        "status": "ready",
        "extensions": sorted(list(exts)),
        "tables_present": table_count,
    }
