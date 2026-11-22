"""Shared, dependency-free helpers for public data download commands."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


USER_AGENT = "flood-aware-emergency-access/0.1 (research data acquisition)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(part.strip()) for part in value.split(","))
    except (ValueError, TypeError) as exc:
        raise ValueError("bbox must be west,south,east,north") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox coordinates are invalid or reversed")
    return west, south, east, north


def bbox_text(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{value:.8f}".rstrip("0").rstrip(".") for value in bbox)


def build_url(url: str, params: Mapping[str, Any] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urllib.parse.urlencode(params, doseq=True)}"


def request_bytes(
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    attempts: int = 4,
    timeout: int = 90,
) -> bytes:
    target = build_url(url, params)
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(target, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(2**attempt)
    raise RuntimeError(f"Request failed after {attempts} attempts: {target}") from last_error


def request_json(
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    attempts: int = 4,
    timeout: int = 90,
) -> Any:
    payload = request_bytes(url, params, attempts=attempts, timeout=timeout)
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        prefix = payload[:160].decode("utf-8", errors="replace")
        raise RuntimeError(f"Expected JSON but received: {prefix!r}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    destination: Path,
    *,
    overwrite: bool = False,
    max_bytes: int | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        return {
            "url": url,
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "status": "existing",
        }

    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if max_bytes is not None and content_length and int(content_length) > max_bytes:
                raise ValueError(f"Remote file exceeds configured size limit: {url}")
            digest = hashlib.sha256()
            written = 0
            with partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise ValueError(f"Download exceeded configured size limit: {url}")
                    handle.write(chunk)
                    digest.update(chunk)
        partial.replace(destination)
        return {
            "url": url,
            "path": str(destination),
            "bytes": written,
            "sha256": digest.hexdigest(),
            "status": "downloaded",
        }
    except Exception:
        if partial.exists():
            partial.unlink()
        raise

