"""Classic mode: the original three-voice idea audit."""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class ClassicEngine(Engine):
    """Audrey audits, Claib reads the market, Vertical AI closes.

    The closer deliberately sees only a short excerpt of the earlier turns, which
    keeps small local models from summarizing instead of synthesizing.
    """

    mode = "classic"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        audrey, claib, vertical = self.persona_set.personas

        yield TurnRequest(
            audrey,
            f"Audit this idea: {topic!r}. What is actually wrong with it? Be specific.",
            1,
        )
        audit = self.history[-1].content if self.history else ""

        yield TurnRequest(
            claib,
            f"The idea is: {topic!r}. The auditor said: {audit[:400]!r}. "
            "What does the market actually want here, and what is the real next move?",
            2,
        )
        market = self.history[-1].content if self.history else ""

        yield TurnRequest(
            vertical,
            f"Topic: {topic!r}. The auditor: {audit[:200]!r}. "
            f"The market read: {market[:200]!r}. What is the one thing worth hearing?",
            3,
        )
