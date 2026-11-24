"""BMAD-lite: the useful half of a build method, in one pass.

BMAD normally spreads analysis, a PRD, architecture, story files, and a dev cycle
across agents and sessions. This engine keeps the roles and the artifacts that
matter — problem, scope, vertical slice, first story, acceptance — and produces
them in a single five-turn session. No phases to schedule, no documents to carry
between chats.
"""

from __future__ import annotations

from typing import Iterator

from .base import Engine, TurnRequest


class BriefEngine(Engine):
    mode = "bmad"

    def turns(self, topic: str) -> Iterator[TurnRequest]:
        analyst, pm, architect, builder, qa = self.persona_set.personas

        yield TurnRequest(
            analyst,
            f"Brief: {topic!r}. Frame the problem, the user, what they do today, "
            "the evidence you actually have, and the assumptions. End with the one "
            "assumption that, if wrong, kills the effort. No solution.",
            1,
        )
        framing = self.history[-1].content if self.history else ""

        yield TurnRequest(
            pm,
            f"Brief: {topic!r}. Analyst framing: {framing[:600]!r}. Write the scope: "
            "one-sentence product, three must-haves, explicit non-goals, one success "
            "metric, and the smallest slice that can ship.",
            2,
        )
        scope = self.history[-1].content if self.history else ""

        yield TurnRequest(
            architect,
            f"Brief: {topic!r}. Framing: {framing[:400]!r}. Scope: {scope[:500]!r}. "
            "Design the vertical slice: components, data flow, interfaces, storage, "
            "one risky dependency, what to defer. Boring tech. Name the failure mode "
            "that would force a redesign.",
            3,
        )
        architecture = self.history[-1].content if self.history else ""

        yield TurnRequest(
            builder,
            f"Brief: {topic!r}. Scope: {scope[:300]!r}. Slice: {architecture[:600]!r}. "
            "Give the first story: files to touch, interfaces, the test to write first, "
            "a timebox, and what done means today.",
            4,
        )
        story = self.history[-1].content if self.history else ""

        yield TurnRequest(
            qa,
            f"Brief: {topic!r}. Scope: {scope[:300]!r}. Story: {story[:400]!r}. "
            "Three acceptance checks, two kill criteria, what to cut if the day runs "
            "short, and a GO/NO-GO with one reason. Under 150 words.",
            5,
        )
