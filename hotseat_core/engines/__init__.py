"""Engine registry for the three conversation flavors."""

from __future__ import annotations

from typing import Any, Mapping

from ..personas import PersonaSet
from .base import Engine, Turn, TurnRequest, render_transcript
from .bmad import BriefEngine
from .classic import ClassicEngine
from .v2_web import DebateEngine
from .v3_agent import PanelEngine, TribunalEngine

ENGINES = {
    "classic": ClassicEngine,
    "v2": DebateEngine,
    "v3.panel": PanelEngine,
    "v3.tribunal": TribunalEngine,
    "bmad": BriefEngine,
}


def build_engine(
    persona_set: PersonaSet,
    client: Any,
    *,
    styles: tuple[str, ...] = (),
    system_directive: str = "",
    model: str | None = None,
    sampling: Mapping[str, Any] | None = None,
    options: Mapping[str, Any] | None = None,
) -> Engine:
    key = f"{persona_set.mode}.{persona_set.variant}" if persona_set.mode == "v3" else persona_set.mode
    engine_class = ENGINES.get(key)
    if engine_class is None:  # pragma: no cover - guarded by the persona registry
        raise ValueError(f"No engine registered for '{key}'.")
    return engine_class(
        persona_set,
        client,
        styles=styles,
        system_directive=system_directive,
        model=model,
        sampling=sampling,
        options=options,
    )


__all__ = [
    "ENGINES",
    "BriefEngine",
    "ClassicEngine",
    "DebateEngine",
    "Engine",
    "PanelEngine",
    "TribunalEngine",
    "Turn",
    "TurnRequest",
    "build_engine",
    "render_transcript",
]
