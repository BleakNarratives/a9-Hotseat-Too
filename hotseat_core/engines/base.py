"""Shared engine runner.

An engine decides *who says what next*; the runner handles model calls, style
composition, events, and operator injection. That split keeps each mode small and
lets the CLI and bridge behave identically.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

from ..personas import Persona, PersonaSet
from ..tuning import clean_response, compose_styles

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
                    "message": f"{persona.name} is speaking",
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

            try:
                content = self.client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=self._system_for(persona),
                    sampling=self._sampling_for(persona),
                    on_chunk=on_chunk,
                )
            except TypeError:
                # A minimal injected client (common in tests and adapters) may not
                # accept on_chunk. Retry without it before reporting a failure.
                content = self.client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=self._system_for(persona),
                    sampling=self._sampling_for(persona),
                )
                if content:
                    on_chunk(content)

            content = clean_response(content)
            if not content:
                content = "[no response]"
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
