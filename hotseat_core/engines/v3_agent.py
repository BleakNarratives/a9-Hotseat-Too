"""v3 mode: the personal panel and the decision tribunal.

Consolidates the old ``hotseat3.py`` panel (Marlowe, Priya, Zero), the
``hotseat_v3.py`` five-role tribunal plus fixer, and the single-advisor Groq
shell, whose provider semantics live in ``providers``. The legacy trees were
removed; see ``docs/LEGACY_NOTES.md`` and Git history.
"""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class PanelEngine(Engine):
    """Marlowe reads the situation, Priya finds the loop, Zero closes."""

    mode = "v3"
    variant = "panel"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        marlowe, priya, zero = self.persona_set.personas

        yield TurnRequest(marlowe, f"The situation: {topic!r}. What is actually going on here?", 1)
        read = self.history[-1].content if self.history else ""

        yield TurnRequest(
            priya,
            f"The situation: {topic!r}. Marlowe said: {read[:400]!r}. "
            "What is the repeating loop, and where does it actually break?",
            2,
        )
        diagnosis = self.history[-1].content if self.history else ""

        yield TurnRequest(
            zero,
            f"The situation: {topic!r}. Marlowe: {read[:200]!r}. Priya: {diagnosis[:200]!r}. "
            "What is underneath this that has not been said?",
            3,
        )


class TribunalEngine(Engine):
    """Four perspectives, then the Fixer returns three ranked actions."""

    mode = "v3"
    variant = "tribunal"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        perspectives = self.persona_set.personas[:-1]
        fixer = self.persona_set.personas[-1]
        answers: list[str] = []

        for index, persona in enumerate(perspectives, start=1):
            yield TurnRequest(
                persona,
                f"The decision brought to the tribunal: {topic!r}. Give your take in "
                "four to six sentences. No preamble.",
                index,
            )
            answers.append(f"{persona.name}: {self.history[-1].content}")

        joined = "\n".join(answers)
        yield TurnRequest(
            fixer,
            f"Topic: {topic!r}. Perspectives:\n{joined}\n\n"
            "Give exactly three ranked next actions. Each names who does it and what "
            "it costs. Numbers only, no explanation beyond the action itself.",
            len(perspectives) + 1,
        )
