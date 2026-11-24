"""Session orchestration shared by the CLI and the bridge."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .config import HotseatConfig
from .engines import Engine, Turn, build_engine, render_transcript
from .personas import get_persona_set
from .providers import ProviderClient
from .storage import SessionStore, StorageError

EventEmitter = Callable[[dict[str, Any]], None]
ClientFactory = Callable[[str, str | None], Any]


def _default_client_factory(provider: str, model: str | None) -> ProviderClient:
    return ProviderClient(provider)


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

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "memory_id": self.memory_id,
            "mode": self.mode,
            "variant": self.variant,
            "topic": self.topic,
            "provider": self.provider,
            "model": self.model,
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
    ) -> Engine:
        selected_provider = (provider or self.config.provider or "auto").strip().lower()
        selected_model = model or self.config.model
        overrides = merge_overrides(
            self.config.persona_overrides(mode, variant), persona_overrides or {}
        )
        persona_set = get_persona_set(mode, variant, overrides=overrides)
        client = self.client_factory(selected_provider, selected_model)
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
            model=selected_model,
            sampling=merged_sampling,
            options=options,
        )

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
        emit: EventEmitter | None = None,
        stop_event: threading.Event | None = None,
        injection: Callable[[], str | None] | None = None,
        save: bool = True,
        session_id: str | None = None,
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
        except Exception as exc:  # provider and unexpected failures alike
            emitter({"type": "error", "session_id": session_id, "message": str(exc)})
            raise

        transcript = render_transcript(
            topic, turns, f"{engine.persona_set.mode}:{engine.persona_set.variant}"
        )
        result = SessionResult(
            mode=engine.persona_set.mode,
            variant=engine.persona_set.variant or "default",
            topic=topic,
            turns=turns,
            transcript=transcript,
            session_id=session_id,
            provider=str(provider_name),
            model=engine.model,
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
            except StorageError as exc:
                emitter(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": f"Session ran, but memory was not saved: {exc}",
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
                "memory_id": result.memory_id,
                "turns": [turn.public() for turn in turns],
                "transcript": transcript,
                "stopped": bool(stop_event and stop_event.is_set()),
            }
        )
        return result
