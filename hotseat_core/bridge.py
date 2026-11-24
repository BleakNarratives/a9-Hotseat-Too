"""Frontend-ready HTTP, SSE, and NDJSON adapter.

The bridge is deliberately dependency-free (stdlib ``http.server``) and local by
default: it binds ``127.0.0.1``, exposes no filesystem listing, and requires a
bearer token if it is ever bound to a non-loopback address.

Endpoints and event payloads are documented in ``FRONTEND_CONTRACT.md``.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .config import HotseatConfig, load_config
from .personas import MODES, get_persona_set, list_modes
from .providers import available_providers, configured_providers
from .runtime import HotseatRuntime, merge_overrides
from .scouts_feed import ScoutFeed
from .storage import SessionStore, StorageError

MAX_BODY_BYTES = 1_000_000
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
STATIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "mobile.html": "text/html; charset=utf-8",
    "mobile.css": "text/css; charset=utf-8",
    "mobile.js": "text/javascript; charset=utf-8",
}
_TOKEN_QUERY = re.compile(r"([?&]token=)[^&\s\"]*", re.IGNORECASE)


def _redact_token(message: str) -> str:
    """Remove bearer tokens embedded in request-query strings from logs."""

    return _TOKEN_QUERY.sub(r"\1[REDACTED]", message)


def _string_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


@dataclass
class SessionJob:
    id: str
    mode: str
    topic: str
    variant: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[queue.Queue[dict[str, Any] | None]] = field(default_factory=list)
    injections: queue.Queue[str] = field(default_factory=queue.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: str | None = None
    scouts: dict[str, Any] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, event: dict[str, Any]) -> None:
        with self.lock:
            self.events.append(event)
            subscribers = list(self.subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def subscribe(
        self, since: int = 0
    ) -> tuple[list[dict[str, Any]], queue.Queue[dict[str, Any] | None]]:
        subscriber: queue.Queue[dict[str, Any] | None] = queue.Queue()
        with self.lock:
            self.subscribers.append(subscriber)
            snapshot = list(self.events[max(0, since) :])
        return snapshot, subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any] | None]) -> None:
        with self.lock:
            if subscriber in self.subscribers:
                self.subscribers.remove(subscriber)

    def finish(self) -> None:
        with self.lock:
            subscribers = list(self.subscribers)
            self.subscribers.clear()
            self.done.set()
        for subscriber in subscribers:
            subscriber.put(None)

    def reopen(self) -> None:
        """Re-arm a finished job for one threaded follow-up pass."""

        with self.lock:
            self.done.clear()
            self.error = None
            self.injections = queue.Queue()
        self.stop_event.clear()

    def public(self, *, since: int = 0) -> dict[str, Any]:
        with self.lock:
            events = list(self.events[max(0, since) :])
        return {
            "session_id": self.id,
            "mode": self.mode,
            "variant": self.variant,
            "topic": self.topic,
            "done": self.done.is_set(),
            "error": self.error,
            "result": self.result,
            "scouts": self.scouts,
            "events": events,
        }


class Bridge:
    """Session manager used by the HTTP server and by tests."""

    def __init__(
        self,
        config: HotseatConfig | None = None,
        *,
        runtime: HotseatRuntime | None = None,
        store: SessionStore | None = None,
        token: str | None = None,
        allowed_origins: tuple[str, ...] = (),
        scout_feed: ScoutFeed | None = None,
        web_dir: str | Path | None = None,
        secret_loader: Any = None,
    ) -> None:
        self.config = config or load_config()
        self.secret_loader = secret_loader
        self.store = store or SessionStore(self.config.db_path, self.config.session_log)
        self.runtime = runtime or HotseatRuntime(self.config, store=self.store)
        self.token = token or None
        self.allowed_origins = tuple(item for item in allowed_origins if item)
        self.jobs: dict[str, SessionJob] = {}
        self.lock = threading.Lock()
        self.scout_feed = scout_feed or ScoutFeed()
        self.scouts_lock = threading.Lock()
        self.last_scouts: dict[str, Any] | None = None
        self.web_dir = (
            Path(web_dir).expanduser().resolve() if web_dir is not None else None
        )
        self.persona_overrides: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    # ── sessions ──────────────────────────────────────────────────────────────
    def start_session(
        self,
        mode: str,
        topic: str,
        *,
        variant: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        styles: tuple[str, ...] | None = None,
        system_directive: str = "",
        sampling: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        persona_overrides: Mapping[str, Any] | None = None,
        scout_context: Any = None,
        role_models: Mapping[str, str] | None = None,
    ) -> SessionJob:
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("A session topic is required.")
        persona_set = self.persona_set(mode, variant, extra_overrides=persona_overrides)
        if role_models:
            known = {persona.key for persona in persona_set.personas}
            unknown = sorted(set(role_models) - known)
            if unknown:
                raise ValueError(
                    "Unknown role model key(s): "
                    + ", ".join(unknown)
                    + ". Choose: "
                    + ", ".join(sorted(known))
                    + "."
                )
        job = SessionJob(
            id=uuid.uuid4().hex[:12],
            mode=persona_set.mode,
            variant=persona_set.variant,
            topic=topic,
        )
        with self.lock:
            self.jobs[job.id] = job

        merged_options = dict(options or {})
        if isinstance(scout_context, str) and scout_context.strip():
            merged_options["scout_context"] = scout_context.strip()
        elif isinstance(scout_context, Mapping) or scout_context is True:
            request = scout_context if isinstance(scout_context, Mapping) else {}
            try:
                report = self.scout_feed.collect(
                    topic,
                    live=bool(request.get("live", True)),
                    urls=_string_list(request.get("urls")),
                    pricing_urls=_string_list(request.get("pricing_urls")),
                )
            except Exception:  # scouting is best-effort; never block the session
                report = None
            if report is not None:
                self._remember_scouts(report.to_dict())
                job.scouts = report.to_dict()
                prompt = report.to_prompt()
                if prompt:
                    merged_options["scout_context"] = prompt
        options = merged_options or None

        overrides = merge_overrides(
            self.persona_overrides.get((persona_set.mode, persona_set.variant or ""), {}),
            persona_overrides or {},
        )

        def injection() -> str | None:
            try:
                return job.injections.get_nowait()
            except queue.Empty:
                return None

        def run() -> None:
            try:
                result = self.runtime.run_session(
                    persona_set.mode,
                    topic,
                    variant=persona_set.variant if persona_set.mode == "v3" else None,
                    provider=provider,
                    model=model,
                    styles=styles,
                    system_directive=system_directive,
                    sampling=sampling,
                    options=options,
                    persona_overrides=overrides,
                    role_models=role_models,
                    emit=job.emit,
                    stop_event=job.stop_event,
                    injection=injection,
                    session_id=job.id,
                )
                job.result = result.public()
            except Exception as exc:  # reported to the client, never raised in a thread
                job.error = str(exc)
            finally:
                job.finish()

        threading.Thread(target=run, name=f"hotseat-{job.id}", daemon=True).start()
        return job

    def get_job(self, session_id: str) -> SessionJob | None:
        with self.lock:
            return self.jobs.get(session_id)

    def _remember_scouts(self, payload: dict[str, Any]) -> None:
        with self.scouts_lock:
            self.last_scouts = payload

    def refresh_scouts(
        self,
        seed: str = "",
        *,
        live: bool = True,
        urls: Iterable[str] | None = None,
        pricing_urls: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Collect a fresh report and make it the latest one the UI can read."""

        report = self.scout_feed.collect(
            seed, live=live, urls=urls, pricing_urls=pricing_urls
        )
        payload = report.to_dict()
        self._remember_scouts(payload)
        return payload

    def latest_scouts(self) -> dict[str, Any] | None:
        with self.scouts_lock:
            return self.last_scouts

    def continue_session(self, session_id: str, message: str) -> SessionJob:
        """Run a threaded follow-up on a finished, persisted session."""

        job = self.get_job(session_id)
        if job is None:
            raise KeyError(session_id)
        if not job.done.is_set():
            raise ValueError("Session is still running; use /inject while it runs.")
        if not job.result or not job.result.get("memory_id"):
            raise ValueError("Session was not saved, so it cannot be continued.")
        text = (message or "").strip()
        if not text:
            raise ValueError("A follow-up message is required.")
        memory_id = job.result["memory_id"]
        job.reopen()

        def injection() -> str | None:
            try:
                return job.injections.get_nowait()
            except queue.Empty:
                return None

        def run() -> None:
            try:
                result = self.runtime.continue_session(
                    job.id,
                    text,
                    memory_id=memory_id,
                    emit=job.emit,
                    stop_event=job.stop_event,
                    injection=injection,
                )
                job.result = result.public()
            except Exception as exc:  # reported to the client, never raised in a thread
                job.error = str(exc)
            finally:
                job.finish()

        threading.Thread(
            target=run, name=f"hotseat-followup-{job.id}", daemon=True
        ).start()
        return job

    def inject(self, session_id: str, message: str) -> None:
        job = self.get_job(session_id)
        if job is None:
            raise KeyError(session_id)
        if job.done.is_set():
            raise ValueError("Session has already finished.")
        text = (message or "").strip()
        if not text:
            raise ValueError("An injection message is required.")
        job.injections.put(text)

    def stop(self, session_id: str) -> None:
        job = self.get_job(session_id)
        if job is None:
            raise KeyError(session_id)
        job.stop_event.set()

    # ── metadata ──────────────────────────────────────────────────────────────
    def persona_set(
        self,
        mode: str,
        variant: str | None = None,
        *,
        extra_overrides: Mapping[str, Any] | None = None,
    ) -> Any:
        probe = get_persona_set(mode, variant)
        overrides = merge_overrides(
            self.config.persona_overrides(mode, probe.variant),
            self.persona_overrides.get((probe.mode, probe.variant or ""), {}),
        )
        if extra_overrides:
            overrides = merge_overrides(overrides, extra_overrides)
        return get_persona_set(mode, probe.variant, overrides=overrides)

    def update_persona(
        self,
        mode: str,
        key: str,
        values: Mapping[str, Any],
        *,
        variant: str | None = None,
    ) -> dict[str, Any]:
        current = self.persona_set(mode, variant)
        persona = current.by_key(key)
        updated = persona.with_overrides(values)
        stored_key = (current.mode, current.variant or "")
        with self.lock:
            section = self.persona_overrides.setdefault(stored_key, {})
            section.setdefault(key, {}).update(
                {
                    field: getattr(updated, field)
                    for field in ("name", "system", "model", "max_tokens", "temperature", "emoji", "color")
                }
            )
            section[key]["styles"] = list(updated.styles)
        return updated.public(include_system=True)

    def modes(self) -> list[dict[str, Any]]:
        results = []
        for meta in list_modes():
            entry = dict(meta)
            entry["personas"] = {
                name: len(MODES[meta["mode"]]["variants"][name]) for name in meta["variants"]
            }
            results.append(entry)
        return results

    def personas(self, mode: str, *, variant: str | None = None, include_system: bool = False) -> dict[str, Any]:
        return self.persona_set(mode, variant).public(include_system=include_system)

    def history(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.store.recent(limit=limit)

    def providers(self) -> list[dict[str, Any]]:
        return available_providers()

    def provider_status(self) -> dict[str, Any]:
        """Expose credential presence only; secret values never cross this boundary."""

        rows = configured_providers(self.secret_loader)
        return {
            "providers": rows,
            "configured": [row["name"] for row in rows if row["configured"]],
            "missing_credentials": [
                row["name"]
                for row in rows
                if row["requires_key"] and not row["configured"]
            ],
        }


class _Handler(BaseHTTPRequestHandler):
    server_version = "HotseatBridge/" + __version__
    protocol_version = "HTTP/1.1"

    @property
    def bridge(self) -> Bridge:
        return self.server.bridge  # type: ignore[attr-defined]

    # ── helpers ───────────────────────────────────────────────────────────────
    def log_message(self, fmt: str, *args: Any) -> None:  # keep stdout clean for NDJSON
        if self.server.verbose:  # type: ignore[attr-defined]
            message = _redact_token(fmt % args)
            sys.stderr.write("%s - %s\n" % (self.address_string(), message))

    def _cors_headers(self) -> dict[str, str]:
        origin = self.headers.get("Origin")
        if origin and origin in self.bridge.allowed_origins:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }
        return {}

    def _authorized(self, query: Mapping[str, list[str]]) -> bool:
        token = self.bridge.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not provided:
            provided = (query.get("token") or [""])[0]
        return provided == token

    def _static_body(self, relative: str) -> bytes | None:
        """Read a whitelisted asset from an override directory or the wheel."""

        root = self.bridge.web_dir
        if root is not None:
            if not root.is_dir():
                return None
            candidate = (root / relative).resolve()
            if root not in candidate.parents or not candidate.is_file():
                return None
            try:
                return candidate.read_bytes()
            except OSError:
                return None
        try:
            resource = resources.files("hotseat_core").joinpath("web").joinpath(relative)
            if not resource.is_file():
                return None
            return resource.read_bytes()
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            return None

    def _serve_static(self, path: str) -> bool:
        if path in ("", "/"):
            relative = "index.html"
        elif path.rstrip("/") == "/m":
            relative = "mobile.html"
        else:
            relative = unquote(path.lstrip("/"))
        if relative not in STATIC_FILES:
            return False
        body = self._static_body(relative)
        if body is None:
            return False
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", STATIC_FILES[relative])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return True
        return True

    def _send_json(
        self, status: int, payload: Any, *, headers: Mapping[str, str] | None = None
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in {**self._cors_headers(), **(headers or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _read_json(self) -> Any:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            raise ValueError("Content-Length is required.")
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError(f"Request body must be at most {MAX_BODY_BYTES} bytes.")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    # ── verbs ─────────────────────────────────────────────────────────────────
    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._cors_headers():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Origin is not allowed."})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self._serve_static(parsed.path):
            return
        if not self._authorized(query):
            self._error(HTTPStatus.UNAUTHORIZED, "Missing or invalid bearer token.")
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]

        try:
            if parts == ["health"]:
                self._send_json(HTTPStatus.OK, {"status": "ok", "version": __version__})
            elif parts == ["modes"]:
                self._send_json(HTTPStatus.OK, {"modes": self.bridge.modes()})
            elif parts == ["providers"]:
                self._send_json(HTTPStatus.OK, {"providers": self.bridge.providers()})
            elif parts == ["providers", "status"]:
                self._send_json(HTTPStatus.OK, self.bridge.provider_status())
            elif parts == ["scouts", "latest"]:
                self._send_json(
                    HTTPStatus.OK,
                    {"report": self.bridge.latest_scouts(), "next": "/scouts/refresh"},
                )
            elif parts == ["personas"]:
                mode = (query.get("mode") or ["classic"])[0]
                variant = (query.get("variant") or [None])[0]
                include_system = (query.get("system") or ["0"])[0].lower() in {"1", "true", "yes"}
                self._send_json(
                    HTTPStatus.OK, self.bridge.personas(mode, variant=variant, include_system=include_system)
                )
            elif parts == ["history"]:
                try:
                    limit = int((query.get("limit") or ["10"])[0])
                except ValueError:
                    self._error(HTTPStatus.BAD_REQUEST, "limit must be an integer.")
                    return
                self._send_json(HTTPStatus.OK, {"sessions": self.bridge.history(limit)})
            elif len(parts) == 2 and parts[0] == "sessions":
                job = self.bridge.get_job(parts[1])
                if job is None:
                    self._error(HTTPStatus.NOT_FOUND, "Unknown session.")
                    return
                try:
                    since = int((query.get("since") or ["0"])[0])
                except ValueError:
                    since = 0
                self._send_json(HTTPStatus.OK, job.public(since=since))
            elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "events":
                job = self.bridge.get_job(parts[1])
                if job is None:
                    self._error(HTTPStatus.NOT_FOUND, "Unknown session.")
                    return
                try:
                    since = max(0, int((query.get("since") or ["0"])[0]))
                except ValueError:
                    since = 0
                self._stream_events(job, since=since)
            else:
                self._error(HTTPStatus.NOT_FOUND, "Unknown endpoint.")
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except StorageError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            self._error(HTTPStatus.UNAUTHORIZED, "Missing or invalid bearer token.")
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        try:
            body = self._read_json()
            if not isinstance(body, Mapping):
                raise ValueError("Request body must be a JSON object.")
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        try:
            if parts == ["sessions"]:
                mode = str(body.get("mode", "classic"))
                topic = str(body.get("topic", ""))
                styles = body.get("styles")
                if isinstance(styles, str):
                    styles = tuple(s.strip() for s in styles.split(",") if s.strip())
                elif isinstance(styles, list):
                    styles = tuple(str(s).strip() for s in styles if str(s).strip())
                else:
                    styles = None
                job = self.bridge.start_session(
                    mode,
                    topic,
                    variant=body.get("variant"),
                    provider=body.get("provider"),
                    model=body.get("model"),
                    styles=styles,
                    system_directive=str(body.get("system_directive", "")),
                    sampling=body.get("sampling") if isinstance(body.get("sampling"), Mapping) else None,
                    options=body.get("options") if isinstance(body.get("options"), Mapping) else None,
                    persona_overrides=body.get("personas") if isinstance(body.get("personas"), Mapping) else None,
                    scout_context=body.get("scout_context"),
                    role_models=body.get("role_models") if isinstance(body.get("role_models"), Mapping) else None,
                )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "session_id": job.id,
                        "mode": job.mode,
                        "variant": job.variant,
                        "events_url": f"/sessions/{job.id}/events",
                    },
                    headers={"Location": f"/sessions/{job.id}"},
                )
            elif parts == ["scouts", "refresh"]:
                report = self.bridge.refresh_scouts(
                    str(body.get("seed", "")),
                    live=bool(body.get("live", True)),
                    urls=_string_list(body.get("urls")),
                    pricing_urls=_string_list(body.get("pricing_urls")),
                )
                self._send_json(HTTPStatus.OK, {"report": report})
            elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "inject":
                self.bridge.inject(parts[1], str(body.get("message", "")))
                self._send_json(HTTPStatus.ACCEPTED, {"queued": True})
            elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "messages":
                self.bridge.continue_session(parts[1], str(body.get("message", "")))
                self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})
            elif len(parts) == 3 and parts[0] == "sessions" and parts[2] == "stop":
                self.bridge.stop(parts[1])
                self._send_json(HTTPStatus.ACCEPTED, {"stopping": True})
            else:
                self._error(HTTPStatus.NOT_FOUND, "Unknown endpoint.")
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "Unknown session.")
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except StorageError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            self._error(HTTPStatus.UNAUTHORIZED, "Missing or invalid bearer token.")
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[0] != "personas":
            self._error(HTTPStatus.NOT_FOUND, "Unknown endpoint.")
            return
        try:
            body = self._read_json()
            if not isinstance(body, Mapping):
                raise ValueError("Request body must be a JSON object.")
            updated = self.bridge.update_persona(
                parts[1], parts[2], body, variant=(query.get("variant") or [None])[0]
            )
            self._send_json(HTTPStatus.OK, {"persona": updated})
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "Unknown persona.")
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    # ── SSE ───────────────────────────────────────────────────────────────────
    def _stream_events(self, job: SessionJob, *, since: int = 0) -> None:
        snapshot, subscriber = job.subscribe(since=since)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.close_connection = True
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()

        try:
            for event in snapshot:
                self._write_sse(event)
            if job.done.is_set():
                return
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    if job.done.is_set():
                        return
                    continue
                if event is None:
                    return
                self._write_sse(event)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        finally:
            job.unsubscribe(subscriber)

    def _write_sse(self, event: Mapping[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        chunk = f"event: {event.get('type', 'message')}\ndata: {payload}\n\n".encode("utf-8")
        self.wfile.write(chunk)
        self.wfile.flush()


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        bridge: Bridge,
        *,
        verbose: bool = False,
    ) -> None:
        super().__init__(address, _Handler)
        self.bridge = bridge
        self.verbose = verbose


def serve(
    bridge: Bridge | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    verbose: bool = False,
) -> BridgeServer:
    """Bind and return a server; the caller decides how to run it."""

    instance = bridge or Bridge()
    host = host or instance.config.bridge_host
    port = instance.config.bridge_port if port is None else int(port)
    if host not in LOOPBACK and not instance.token:
        raise ValueError(
            "Refusing to bind the bridge to a non-loopback address without --token."
        )
    return BridgeServer((host, port), instance, verbose=verbose)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the Hotseat HTTP/SSE bridge."
    )
    parser.add_argument("--host", default=None, help="Bind address (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default 8765).")
    parser.add_argument("--token", default=None, help="Bearer token required by clients.")
    parser.add_argument("--allow-origin", action="append", default=[], help="Allowed CORS origin.")
    parser.add_argument("--verbose", action="store_true", help="Log requests to stderr.")
    args = parser.parse_args(argv)

    bridge = Bridge(token=args.token, allowed_origins=tuple(args.allow_origin))
    server = serve(bridge, host=args.host, port=args.port, verbose=args.verbose)
    host, port = server.server_address[:2]
    print(f"Hotseat bridge listening on http://{host}:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
