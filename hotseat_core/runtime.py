"""Session orchestration shared by the CLI and the bridge."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .config import HotseatConfig
from .engines import Engine, FollowUpEngine, Turn, build_engine, render_transcript
from .personas import get_persona_set
from .providers import PROVIDERS, ProviderClient, build_client
from .storage import SessionStore, StorageError

EventEmitter = Callable[[dict[str, Any]], None]
ClientFactory = Callable[[str, str | None], Any]
logger = logging.getLogger(__name__)


def _default_client_factory(provider: str, model: str | None) -> Any:
    return build_client(provider, model)


def merge_overrides(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = {key: dict(value) for key, value in first.items() if isinstance(value, Mapping)}
    for key, value in second.items():
        if isinstance(value, Mapping):
            merged.setdefault(key, {}).update(value)
        else:
            merged[key] = value
    return merged


@dataclass
class SessionResult:
    mode: str
    variant: str
    topic: str
    turns: list[Turn] = field(default_factory=list)
    transcript: str = ""
    session_id: str = ""
    memory_id: int | None = None
    provider: str = ""
    model: str | None = None
    fallback_used: bool = False
    fallback_trail: list[str] = field(default_factory=list)
    key: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "memory_id": self.memory_id,
            "mode": self.mode,
            "variant": self.variant,
            "topic": self.topic,
            "provider": self.provider,
            "model": self.model,
            "fallback_used": self.fallback_used,
            "fallback_trail": list(self.fallback_trail),
            "key": self.key,
            "transcript": self.transcript,
            "turns": [turn.public() for turn in self.turns],
        }


class HotseatRuntime:
    """Resolve a mode, run it, stream events, and persist the result."""

    def __init__(
        self,
        config: HotseatConfig,
        *,
        store: SessionStore | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.config = config
        self.store = store or SessionStore(config.db_path, config.session_log)
        self.client_factory = client_factory or _default_client_factory

    def build_engine(
        self,
        mode: str,
        *,
        variant: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        styles: tuple[str, ...] | None = None,
        system_directive: str = "",
        sampling: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        persona_overrides: Mapping[str, Any] | None = None,
        role_models: Mapping[str, str] | None = None,
        cast: Sequence[str] | None = None,
    ) -> Engine:
        selected_provider = (provider or self.config.provider or "auto").strip().lower()
        selected_model = model or self.config.model
        overrides = merge_overrides(
            self.config.persona_overrides(mode, variant), persona_overrides or {}
        )
        role_overrides: dict[str, Any] = {}
        configured_roles = self.config.role_models_for(mode, variant)
        for key, value in configured_roles.items():
            if value not in (None, ""):
                role_overrides[str(key)] = {"model": str(value).strip()}
        for key, value in (role_models or {}).items():
            model_name = value.get("model") if isinstance(value, Mapping) else value
            if model_name not in (None, ""):
                role_overrides[str(key)] = {"model": str(model_name).strip()}
        if role_overrides:
            overrides = merge_overrides(overrides, role_overrides)
        persona_set = get_persona_set(mode, variant, overrides=overrides, cast=cast)
        if role_overrides:
            known = {persona.key for persona in persona_set.personas}
            unknown = sorted(set(role_overrides) - known)
            if unknown:
                raise ValueError(
                    "Unknown role model key(s): "
                    + ", ".join(unknown)
                    + ". Choose: "
                    + ", ".join(sorted(known))
                    + "."
                )
        route_provider, route_model = self._seat_route(
            persona_set,
            selected_provider,
            selected_model,
            explicit_roles=bool(role_overrides),
        )
        engine_model = route_model or selected_model
        client = self.client_factory(route_provider, route_model)
        merged_sampling: dict[str, Any] = {}
        configured_sampling = self.config.provider_options.get("sampling")
        if isinstance(configured_sampling, Mapping):
            merged_sampling.update(configured_sampling)
        if sampling:
            merged_sampling.update(sampling)
        return build_engine(
            persona_set,
            client,
            styles=styles if styles is not None else self.config.styles,
            system_directive=system_directive,
            model=engine_model,
            sampling=merged_sampling,
            options=options,
        )

    @staticmethod
    def _seat_route(
        persona_set: Any,
        provider: str,
        model: str | None,
        *,
        explicit_roles: bool = False,
    ) -> tuple[str, str | None]:
        """Optionally spread sessions across the active provider pools.

        The key ring already rotates on every call and falls through on a
        failure. This adds a session-level starting point so a busy install with
        several free-tier keys does not put every session on the same provider.
        """

        if explicit_roles or model or (provider or "").strip().lower() not in {"", "auto"}:
            return provider, model
        enabled = os.environ.get("HOTSEAT_SEAT_ROUTER", "").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return provider, model
        try:
            from .moe_router import pick_seat_route

            route_provider, route_model = pick_seat_route(
                persona_set.personas[0].key if persona_set.personas else "critic",
                randomize=True,
            )
        except (ImportError, OSError, ValueError):
            return provider, model
        if route_provider in PROVIDERS and route_model:
            return route_provider, route_model
        return provider, model

    def run_session(
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
        role_models: Mapping[str, str] | None = None,
        emit: EventEmitter | None = None,
        stop_event: threading.Event | None = None,
        injection: Callable[[], str | None] | None = None,
        save: bool = True,
        session_id: str | None = None,
        cast: Sequence[str] | None = None,
    ) -> SessionResult:
        emitter = emit or (lambda event: None)
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("A session topic is required.")

        session_id = session_id or uuid.uuid4().hex[:12]
        engine = self.build_engine(
            mode,
            variant=variant,
            provider=provider,
            model=model,
            styles=styles,
            system_directive=system_directive,
            sampling=sampling,
            options=options,
            persona_overrides=persona_overrides,
            role_models=role_models,
            cast=cast,
        )
        provider_name = getattr(engine.client, "provider", provider or self.config.provider)
        started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        emitter(
            {
                "type": "session_start",
                "session_id": session_id,
                "timestamp": started,
                "mode": engine.persona_set.mode,
                "variant": engine.persona_set.variant,
                "label": engine.persona_set.label,
                "topic": topic,
                "provider": provider_name,
                "model": engine.model,
                "role_models": dict(role_models or {}),
                "personas": [
                    persona.public() for persona in engine.persona_set.personas
                ],
            }
        )

        turns: list[Turn] = []
        try:
            turns = engine.run(
                topic, emit=emitter, stop_event=stop_event, injection=injection
            )
        except Exception:  # provider and unexpected failures alike
            logger.exception("session failed session_id=%s mode=%s", session_id, mode)
            emitter(
                {
                    "type": "error",
                    "session_id": session_id,
                    "message": "The room hit a snag. Give that case another try.",
                }
            )
            raise

        transcript = render_transcript(
            topic, turns, f"{engine.persona_set.mode}:{engine.persona_set.variant}"
        )
        client = engine.client
        result = SessionResult(
            mode=engine.persona_set.mode,
            variant=engine.persona_set.variant or "default",
            topic=topic,
            turns=turns,
            transcript=transcript,
            session_id=session_id,
            provider=str(getattr(client, "provider", provider_name)),
            model=getattr(client, "model", None) or engine.model,
            fallback_used=bool(getattr(client, "fallback_used", False)),
            fallback_trail=list(getattr(client, "attempts", []) or []),
            key=str(getattr(client, "key_label", "") or "") or None,
        )

        if save and turns:
            try:
                result.memory_id = self.store.save_session(
                    mode=result.mode,
                    topic=topic,
                    turns=[turn.public() for turn in turns],
                    transcript=transcript,
                    provider=result.provider,
                    model=result.model,
                    timestamp=started,
                )
                emitter(
                    {
                        "type": "memory_saved",
                        "session_id": session_id,
                        "path": str(self.store.db_path),
                        "memory_id": result.memory_id,
                    }
                )
            except StorageError:
                logger.exception("session memory was not saved session_id=%s", session_id)
                emitter(
                    {
                        "type": "status",
                        "session_id": session_id,
                        "message": "The room finished. This session was not saved.",
                    }
                )

        emitter(
            {
                "type": "session_end",
                "session_id": session_id,
                "timestamp": started,
                "mode": result.mode,
                "variant": result.variant,
                "topic": topic,
                "provider": result.provider,
                "model": result.model,
                "fallback_used": result.fallback_used,
                "fallback_trail": result.fallback_trail,
                "key": result.key,
                "memory_id": result.memory_id,
                "turns": [turn.public() for turn in turns],
                "transcript": transcript,
                "stopped": bool(stop_event and stop_event.is_set()),
            }
        )
        return result

    def continue_session(
        self,
        session_id: str,
        message: str,
        *,
        memory_id: int | str | None = None,
        emit: EventEmitter | None = None,
        stop_event: threading.Event | None = None,
        injection: Callable[[], str | None] | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> SessionResult:
        """Append one operator follow-up to a finished, persisted session."""

        emitter = emit or (lambda event: None)
        instruction = (message or "").strip()
        if not instruction:
            raise ValueError("A follow-up message is required.")
        stored = self.store.get(memory_id if memory_id is not None else session_id)
        if not stored:
            raise ValueError(
                "Unknown session. Follow-ups require a persisted session with a memory id."
            )
        persisted_id = int(stored["id"]) if stored.get("id") is not None else None

        mode = str(stored.get("mode") or "classic")
        variant = "panel" if mode == "v3" else None
        persona_set = get_persona_set(
            mode,
            variant,
            overrides=self.config.persona_overrides(mode, variant),
        )
        selected_provider = (
            provider or stored.get("provider") or self.config.provider or "auto"
        )
        selected_model = model or stored.get("model") or self.config.model
        client = self.client_factory(str(selected_provider), selected_model)
        engine = FollowUpEngine(
            persona_set,
            client,
            styles=self.config.styles,
            model=selected_model,
        )
        prior = [
            Turn(
                persona=str(turn.get("persona") or "unknown"),
                speaker=str(turn.get("speaker") or turn.get("persona") or "unknown"),
                content=str(turn.get("content") or ""),
                round=int(turn.get("round") or 0),
                model=turn.get("model"),
            )
            for turn in stored.get("turns") or []
        ]
        engine.history = list(prior)
        provider_name = getattr(client, "provider", selected_provider)
        started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        emitter(
            {
                "type": "operator_message",
                "session_id": session_id,
                "timestamp": started,
                "message": instruction,
            }
        )
        emitter(
            {
                "type": "iteration_start",
                "session_id": session_id,
                "timestamp": started,
                "iteration": 2,
                "parent_turns": len(prior),
            }
        )

        try:
            turns = engine.run(
                instruction, emit=emitter, stop_event=stop_event, injection=injection
            )
        except Exception:
            logger.exception(
                "follow-up failed session_id=%s memory_id=%s", session_id, persisted_id
            )
            emitter(
                {
                    "type": "error",
                    "session_id": session_id,
                    "message": "The room hit a snag. Give that follow-up another try.",
                }
            )
            raise

        all_turns = prior + turns
        transcript = render_transcript(
            str(stored.get("topic") or "Untitled"),
            all_turns,
            f"{mode}:{persona_set.variant or 'default'}",
        )
        try:
            if persisted_id is None:
                raise StorageError("The session has no memory id.")
            self.store.append_turns(
                persisted_id,
                turns=[turn.public() for turn in all_turns],
                transcript=transcript,
            )
            emitter(
                {
                    "type": "memory_saved",
                    "session_id": session_id,
                    "path": str(self.store.db_path),
                    "memory_id": persisted_id,
                }
            )
        except StorageError:
            logger.exception("follow-up memory was not saved session_id=%s", session_id)
            emitter(
                {
                    "type": "status",
                    "session_id": session_id,
                    "message": "The room finished. This follow-up was not saved.",
                }
            )

        result = SessionResult(
            mode=mode,
            variant=persona_set.variant or "default",
            topic=str(stored.get("topic") or "Untitled"),
            turns=all_turns,
            transcript=transcript,
            session_id=session_id,
            memory_id=persisted_id,
            provider=str(getattr(client, "provider", provider_name)),
            model=getattr(client, "model", None) or selected_model,
            fallback_used=bool(getattr(client, "fallback_used", False)),
            fallback_trail=list(getattr(client, "attempts", []) or []),
            key=str(getattr(client, "key_label", "") or "") or None,
        )
        emitter(
            {
                "type": "session_end",
                "session_id": session_id,
                "timestamp": started,
                "mode": result.mode,
                "variant": result.variant,
                "topic": result.topic,
                "provider": result.provider,
                "model": result.model,
                "fallback_used": result.fallback_used,
                "fallback_trail": result.fallback_trail,
                "key": result.key,
                "memory_id": result.memory_id,
                "iteration": 2,
                "follow_up": True,
                "turns": [turn.public() for turn in all_turns],
                "transcript": transcript,
                "stopped": bool(stop_event and stop_event.is_set()),
            }
        )
        return result
