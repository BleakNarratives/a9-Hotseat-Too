"""Shared engine runner.

An engine decides *who says what next*; the runner handles model calls, style
composition, events, and operator injection. That split keeps each mode small and
lets the CLI and bridge behave identically.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

from ..personas import Persona, PersonaSet
from ..providers import ProviderError, demo_response
from ..tuning import clean_response, compose_styles

logger = logging.getLogger(__name__)

EventEmitter = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class TurnRequest:
    persona: Persona
    prompt: str
    round: int


@dataclass
class Turn:
    persona: str
    speaker: str
    content: str
    round: int
    model: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "persona": self.persona,
            "speaker": self.speaker,
            "content": self.content,
            "round": self.round,
            "model": self.model,
        }


class Engine:
    """Base class for the three conversation flavors."""

    mode = "base"

    def __init__(
        self,
        persona_set: PersonaSet,
        client: Any,
        *,
        styles: tuple[str, ...] = (),
        system_directive: str = "",
        model: str | None = None,
        sampling: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self.persona_set = persona_set
        self.client = client
        self.styles = tuple(styles)
        self.system_directive = system_directive.strip()
        self.model = model
        self.sampling = dict(sampling or {})
        self.options = dict(options or {})
        self.history: list[Turn] = []
        self.host_note: str | None = None

    # Engines implement this as a generator so each prompt can reference the
    # turns produced before it.
    def turns(self, topic: str) -> Iterator[TurnRequest]:  # pragma: no cover - abstract
        raise NotImplementedError

    def _sampling_for(self, persona: Persona) -> dict[str, Any]:
        composed = compose_styles(persona.styles + self.styles, configured=self.sampling)
        values = dict(composed["sampling"])
        values["temperature"] = persona.temperature
        values["max_tokens"] = persona.max_tokens
        overrides = self.sampling.get("sampling_overrides", {})
        if isinstance(overrides, Mapping):
            values.update(overrides)
        return values

    def _system_for(self, persona: Persona) -> str:
        composed = compose_styles(persona.styles + self.styles, configured=self.sampling)
        parts = [persona.system]
        if self.system_directive:
            parts.append(self.system_directive)
        if composed["system_directive"]:
            parts.append(composed["system_directive"])
        return "\n\n".join(part for part in parts if part)

    def _take_injection(self, injection: Callable[[], str | None] | None) -> str | None:
        if injection is not None:
            note = injection()
            if note:
                self.host_note = note
        note = self.host_note
        self.host_note = None
        return note

    def _complete_turn(
        self,
        persona: Persona,
        prompt: str,
        model: str | None,
        *,
        on_chunk: Callable[[str], None],
        emitter: EventEmitter,
        stop_event: threading.Event | None,
    ) -> str:
        """Get one character turn, retrying quietly before showing a failure.

        The fallback client already walks the key ring, models, and providers.
        This loop covers the case where the whole ring is cooling down at once:
        it waits and tries again instead of putting a provider status code in
        front of the room. If every attempt fails, a deterministic house reply
        keeps the character's seat occupied rather than rendering a blank card.
        """

        messages = [{"role": "user", "content": prompt}]
        system = self._system_for(persona)
        sampling = self._sampling_for(persona)
        delays = (0.0, 2.0, 5.0)
        last_error: Exception | None = None

        for attempt, delay in enumerate(delays):
            if stop_event is not None and stop_event.is_set():
                return ""
            if delay:
                emitter(
                    {
                        "type": "status",
                        "message": "The room is taking a second pass.",
                        "persona": persona.key,
                        "round": 0,
                        "retrying": True,
                    }
                )
                if stop_event is not None:
                    if stop_event.wait(delay):
                        return ""
                else:
                    time.sleep(delay)
            try:
                try:
                    content = self.client.complete(
                        messages=messages,
                        model=model,
                        system=system,
                        sampling=sampling,
                        on_chunk=on_chunk,
                    )
                except TypeError:
                    # A minimal injected client (common in tests and adapters) may
                    # not accept on_chunk. Retry without it before reporting a failure.
                    content = self.client.complete(
                        messages=messages,
                        model=model,
                        system=system,
                        sampling=sampling,
                    )
                    if content:
                        on_chunk(content)
                cleaned = clean_response(content)
                if cleaned:
                    return cleaned
                raise ProviderError(
                    "The provider returned an empty reply.",
                    retryable=True,
                    kind="empty",
                )
            except Exception as exc:  # a bad key, a cold key, or a bad reply
                last_error = exc
                logger.warning(
                    "character turn failed persona=%s attempt=%s kind=%s status=%s",
                    persona.key,
                    attempt + 1,
                    getattr(exc, "kind", type(exc).__name__),
                    getattr(exc, "status_code", None),
                )
                if attempt + 1 < len(delays):
                    continue
                break

        # Last resort: keep the seat warm with a deterministic in-character
        # answer. Details stay in the server log; the room only sees prose.
        logger.error(
            "using house fallback persona=%s after %s failed attempts: %s",
            persona.key,
            len(delays),
            type(last_error).__name__ if last_error else "empty reply",
        )
        fallback = clean_response(demo_response(system, messages))
        return fallback or "The room is still working. Give it one more moment."

    def run(
        self,
        topic: str,
        *,
        emit: EventEmitter | None = None,
        stop_event: threading.Event | None = None,
        injection: Callable[[], str | None] | None = None,
    ) -> list[Turn]:
        emitter = emit or (lambda event: None)
        produced: list[Turn] = []
        for request in self.turns(topic):
            if stop_event is not None and stop_event.is_set():
                break
            persona = request.persona
            note = self._take_injection(injection)
            prompt = request.prompt
            if note:
                prompt = f"{prompt}\n\nOperator note, weigh this before answering: {note}"

            emitter(
                {
                    "type": "status",
                    "message": "The room is listening.",
                    "persona": persona.key,
                    "round": request.round,
                }
            )
            model = self.model or persona.model
            chunks: list[str] = []

            def on_chunk(text: str, *, _persona: str = persona.key) -> None:
                if not text:
                    return
                chunks.append(text)
                emitter({"type": "token_chunk", "persona": _persona, "text": text})

            content = self._complete_turn(
                persona,
                prompt,
                model,
                on_chunk=on_chunk,
                emitter=emitter,
                stop_event=stop_event,
            )
            if not content:
                break
            turn = Turn(
                persona=persona.key,
                speaker=persona.name,
                content=content,
                round=request.round,
                model=model,
            )
            self.history.append(turn)
            produced.append(turn)
            emitter({"type": "persona_turn", **turn.public()})
        return produced


def render_transcript(topic: str, turns: list[Turn], mode: str) -> str:
    """Render a Markdown transcript suitable for the UI, logs, and README."""

    lines = ["# The Hot Seat", "", f"**Mode:** {mode}", "", f"## {topic}", ""]
    for turn in turns:
        lines.extend((f"### {turn.speaker}", "", turn.content.strip(), ""))
    return "\n".join(lines).rstrip() + "\n"
