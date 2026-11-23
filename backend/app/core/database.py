import logging
from contextlib import contextmanager
from fastapi import HTTPException
from psycopg import connect
from psycopg.rows import dict_row

from backend.app.core.config import settings
from backend.app.core.errors import sanitize_sensitive_string

logger = logging.getLogger("emergency_access.db")


@contextmanager
def db():
    dsn = settings.DATABASE_URL
    if not dsn:
        logger.error("DATABASE_URL is not configured")
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL is not configured",
        )
    try:
        with connect(
            dsn,
            row_factory=dict_row,
            connect_timeout=settings.CONNECT_TIMEOUT_S,
        ) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"set statement_timeout = '{settings.STATEMENT_TIMEOUT_MS}ms'")
            except Exception:
                pass  # Graceful fallback for poolers in transaction mode
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        sanitized_msg = sanitize_sensitive_string(str(exc))
        logger.error("Database connection failure: %s", sanitized_msg)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None


def fetch_all(query: str, params=()) -> list[dict]:
    with db() as conn:
        return conn.execute(query, params).fetchall()


def fetch_one(query: str, params=()) -> dict | None:
    with db() as conn:
        return conn.execute(query, params).fetchone()
