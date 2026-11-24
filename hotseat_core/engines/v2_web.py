"""v2 mode: the web debate, without Gradio.

This consolidates the old ``hotseat_v2/app.py`` and
``hotseat_v2/app_v2_maybe_idk.py`` (removed; see ``docs/LEGACY_NOTES.md``).
The two legacy files differed only in sleep timing and small prompt wording; the
engine keeps the useful shape — three skeptics, then the volunteer answers them.
"""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class DebateEngine(Engine):
    mode = "v2"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        skeptics = self.persona_set.personas[:3]
        volunteer = self.persona_set.personas[3]
        statement = str(self.options.get("statement", "")).strip()
        opening = f" The volunteer's opening statement: {statement!r}." if statement else ""

        critiques: list[str] = []
        for index, skeptic in enumerate(skeptics, start=1):
            yield TurnRequest(
                skeptic,
                f"The idea: {topic!r}.{opening} Tear it apart with brutal logic and "
                "concrete evidence. What breaks first?",
                index,
            )
            critiques.append(f"{skeptic.name}: {self.history[-1].content}")

        joined = "\n".join(critiques)
        yield TurnRequest(
            volunteer,
            f"Defend the idea {topic!r} against these critiques:\n{joined}\n\n"
            "Concede what is genuinely broken, counter what is overstated, and name "
            "the smallest change that makes the idea survive.",
            4,
        )
