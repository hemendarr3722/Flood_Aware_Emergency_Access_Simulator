import re
from typing import Any
from pydantic import BaseModel


def sanitize_sensitive_string(val: str) -> str:
    """Strip password components from URLs and connection strings."""
    if not val:
        return val
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", val)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    detail: str
    error: ErrorDetail
