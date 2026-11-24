"""Threaded follow-up iteration.

A finished session can be questioned in place. The closer persona answers with the
prior transcript in view and states what changes, so a brief can be revised
conversationally without re-running the whole arena.
"""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class FollowUpEngine(Engine):
    mode = "followup"

    def turns(self, instruction: str) -> Iterator[TurnRequest]:
        persona = self.persona_set.personas[-1]
        prior = "\n\n".join(
            f"{turn.speaker}: {turn.content[:900]}" for turn in self.history[-9:]
        )
        yield TurnRequest(
            persona,
            "Prior session transcript (oldest to newest):\n"
            f"{prior[:2200]}\n\n"
            f"Operator follow-up: {instruction}\n\n"
            f"Answer as {persona.name}, directly to the operator. Reference the prior "
            "work, state what changes, and give the concrete revision. If the "
            "instruction cannot be honored, say what is missing. No preamble.",
            len(self.history) + 1,
        )
