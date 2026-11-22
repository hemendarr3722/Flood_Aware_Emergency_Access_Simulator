import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    DATABASE_URL: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL"))
    ALLOWED_ORIGINS: list[str] = field(
        default_factory=lambda: [
            x.strip()
            for x in os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
            ).split(",")
            if x.strip()
        ]
    )
    CONNECT_TIMEOUT_S: int = 8
    STATEMENT_TIMEOUT_MS: int = 8000
    MAX_ROAD_FEATURES: int = 3000
    MAX_FACILITY_FEATURES: int = 500
    MAX_BBOX_SPAN_DEG: float = 0.5  # Max bbox width/height ~55km to prevent unbounded queries
    API_TITLE: str = "Flood-Aware Emergency Access API"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = (
        "Production portfolio API for flood-aware emergency access simulation in Houston pilot area. "
        "Planning and research simulation only — NOT for live tactical emergency response or real-time navigation."
    )


settings = Settings()
