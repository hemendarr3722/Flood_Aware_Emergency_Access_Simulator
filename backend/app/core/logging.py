import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)

logger = logging.getLogger("emergency_access.api")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = req_id

        start_time = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["x-request-id"] = req_id

        # Redact any passwords/tokens from the path/query
        url_path = request.url.path
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s",
            req_id,
            request.method,
            url_path,
            response.status_code,
            duration_ms,
        )
        return response
