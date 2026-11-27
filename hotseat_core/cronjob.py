"""cron-job.org REST client for keeping a public Hot Seat awake.

The bridge is one long-lived process. A free host sleeps it after idle
minutes, so cron-job.org can GET the public room on a schedule. The API key is
only used by the setup command; the bridge never needs it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

API_ROOT = "https://api.cron-job.org"
DEFAULT_TITLE = "Hot Seat keepalive"
DEFAULT_INTERVAL_MINUTES = 10
Transport = Callable[[urllib.request.Request, float], tuple[int, bytes]]


class CronJobError(RuntimeError):
    """cron-job.org rejected a request or could not be reached."""


def _default_transport(
    request: urllib.request.Request, timeout: float
) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CronJobError(f"cron-job.org is unreachable: {exc}") from exc


def _request(
    api_key: str,
    method: str,
    path: str,
    *,
    payload: Any = None,
    timeout: float = 15.0,
    transport: Transport | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise CronJobError(
            "CRONJOB_API_KEY is not set. Create an API key in the cron-job.org "
            "Console under Settings, then add it in the Keys tab."
        )
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API_ROOT + path, data=data, method=method)
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    status, body = (transport or _default_transport)(request, timeout)
    text = body.decode("utf-8", "replace").strip()
    if status >= 400:
        raise CronJobError(
            f"cron-job.org {method} {path} failed ({status}): "
            f"{text or 'no response body'}"
        )
    if not text:
        return {}
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CronJobError(
            f"cron-job.org returned invalid JSON for {method} {path}."
        ) from exc
    return decoded if isinstance(decoded, dict) else {}


def _public_room_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse((base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "A public http(s) base URL is required, e.g. "
            "https://hotseat.onrender.com."
        )
    if parsed.username or parsed.password:
        raise ValueError("The public URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("The public URL must not contain a query or fragment.")
    return base_url.strip().rstrip("/") + "/"


def _minutes(interval_minutes: int) -> list[int]:
    if interval_minutes < 1 or interval_minutes > 60:
        raise ValueError("The keepalive interval must be between 1 and 60 minutes.")
    if interval_minutes == 1:
        return [-1]
    return list(range(0, 60, interval_minutes))


def _schedule(interval_minutes: int) -> dict[str, Any]:
    return {
        "timezone": "UTC",
        "expiresAt": 0,
        "hours": [-1],
        "mdays": [-1],
        "minutes": _minutes(interval_minutes),
        "months": [-1],
        "wdays": [-1],
    }


def list_jobs(
    api_key: str, *, timeout: float = 15.0, transport: Transport | None = None
) -> list[dict[str, Any]]:
    """Return every job in the account."""

    payload = _request(
        api_key, "GET", "/jobs", timeout=timeout, transport=transport
    )
    jobs = payload.get("jobs")
    return jobs if isinstance(jobs, list) else []


def ensure_keepalive(
    api_key: str,
    base_url: str,
    *,
    title: str = DEFAULT_TITLE,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    timeout: float = 15.0,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Create the public room keepalive, or update the job with the same title.

    Returns a small summary with ``action`` (``created`` or ``updated``), the
    cron-job.org job id, the exact URL, and the schedule.
    """

    room_url = _public_room_url(base_url)
    interval = int(interval_minutes)
    schedule = _schedule(interval)
    job = {
        "url": room_url,
        "title": title.strip() or DEFAULT_TITLE,
        "enabled": True,
        "saveResponses": False,
        "requestMethod": 0,
        "requestTimeout": 30,
        "schedule": schedule,
    }

    jobs = list_jobs(api_key, timeout=timeout, transport=transport)
    existing = next(
        (item for item in jobs if str(item.get("title", "")) == job["title"]),
        None,
    )
    if existing is not None:
        job_id = existing.get("jobId")
        if job_id is None:
            raise CronJobError("cron-job.org returned a job without a job id.")
        _request(
            api_key,
            "PATCH",
            f"/jobs/{job_id}",
            payload={"job": job},
            timeout=timeout,
            transport=transport,
        )
        return {
            "action": "updated",
            "job_id": job_id,
            "title": job["title"],
            "url": room_url,
            "interval_minutes": interval,
        }

    created = _request(
        api_key,
        "PUT",
        "/jobs",
        payload={"job": job},
        timeout=timeout,
        transport=transport,
    )
    return {
        "action": "created",
        "job_id": created.get("jobId"),
        "title": job["title"],
        "url": room_url,
        "interval_minutes": interval,
    }
