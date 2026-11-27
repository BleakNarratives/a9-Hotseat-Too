"""Custom cast: the user's own call, one turn each, in order.

The persona prompts do the character work; this engine only supplies the case,
the recent history, and a hard instruction to take a position and stop.
"""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class CustomCastEngine(Engine):
    mode = "custom"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        if not self.persona_set.personas:
            raise ValueError("A custom cast needs at least one persona.")
        for index, persona in enumerate(self.persona_set.personas, start=1):
            prior = "\n".join(
                f"{turn.speaker}: {turn.content[:500]}" for turn in self.history[-4:]
            )
            context = f"What has been said so far:\n{prior}\n\n" if prior else ""
            yield TurnRequest(
                persona,
                f"The case on the table: {topic!r}.\n\n"
                f"{context}"
                "Give your read in character, in three to six sentences. Take a "
                "position, name the risk you see, and stop. No preamble, no summary "
                "of the case, no list of questions.",
                index,
            )
