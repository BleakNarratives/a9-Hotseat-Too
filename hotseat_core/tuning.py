"""Composable persona style profiles and lightweight response cleanup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class StyleProfile:
    directive: str
    sampling: Mapping[str, Any]


# Sampling values are conservative defaults. Callers may override any value in
# a profile, and role-specific overrides are applied last.
STYLE_PROFILES: dict[str, StyleProfile] = {
    "noslop": StyleProfile(
        "Answer directly. Remove generic praise, filler, repeated conclusions, and canned transitions. Use concrete details.",
        {"temperature": 0.65, "top_p": 0.9, "frequency_penalty": 0.25, "presence_penalty": 0.0, "max_tokens": 1400},
    ),
    "nosyco": StyleProfile(
        "Do not open with a greeting, apology, or self-referential disclaimer. Do not claim certainty without support. Be candid and specific.",
        {"temperature": 0.65, "top_p": 0.9, "frequency_penalty": 0.2, "presence_penalty": 0.0, "max_tokens": 1400},
    ),
    "terse": StyleProfile(
        "Prefer the shortest complete answer that solves the task. Put the answer first; omit preamble and repetition.",
        {"temperature": 0.55, "top_p": 0.85, "frequency_penalty": 0.2, "presence_penalty": 0.0, "max_tokens": 1400},
    ),
    "adversarial_critic": StyleProfile(
        "Stress-test claims and plans. Identify assumptions, failure modes, and evidence gaps; distinguish facts from hypotheses. Critique the work, not the person, and include a viable improvement when possible.",
        {"temperature": 0.75, "top_p": 0.92, "frequency_penalty": 0.15, "presence_penalty": 0.1, "max_tokens": 1400},
    ),
}

_DEFAULT_SAMPLING: dict[str, Any] = {
    "temperature": 0.7,
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "max_tokens": 1400,
}


def compose_styles(
    styles: str | Sequence[str] | None = None,
    *,
    role: str | None = None,
    configured: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose style directives and sampling values in listed order.

    ``configured`` may contain ``sampling`` defaults and a ``roles`` mapping,
    e.g. ``{"roles": {"critic": {"temperature": 0.8}}}``. A role block may
    also contain a ``styles`` list and its own ``sampling`` overrides.
    Unknown style names are rejected rather than silently ignored.
    """

    if styles is None:
        names: list[str] = []
    elif isinstance(styles, str):
        names = [name.strip() for name in styles.split(",") if name.strip()]
    else:
        names = [str(name).strip() for name in styles if str(name).strip()]

    config = dict(configured or {})
    role_config: Mapping[str, Any] = {}
    roles = config.get("roles", {})
    if role and isinstance(roles, Mapping) and isinstance(roles.get(role), Mapping):
        role_config = roles[role]
        extra_styles = role_config.get("styles", ())
        if isinstance(extra_styles, str):
            names.extend(s.strip() for s in extra_styles.split(",") if s.strip())
        elif isinstance(extra_styles, Sequence):
            names.extend(str(s).strip() for s in extra_styles if str(s).strip())

    directives: list[str] = []
    sampling = dict(_DEFAULT_SAMPLING)
    base_sampling = config.get("sampling", {})
    if isinstance(base_sampling, Mapping):
        sampling.update(base_sampling)

    for name in names:
        if name not in STYLE_PROFILES:
            raise ValueError(f"Unknown style modifier '{name}'. Available: {', '.join(STYLE_PROFILES)}.")
        profile = STYLE_PROFILES[name]
        if profile.directive not in directives:
            directives.append(profile.directive)
        sampling.update(profile.sampling)

    profile_overrides = config.get("sampling_overrides", {})
    if isinstance(profile_overrides, Mapping):
        sampling.update(profile_overrides)
    role_sampling = role_config.get("sampling", {})
    if isinstance(role_sampling, Mapping):
        sampling.update(role_sampling)

    return {"system_directive": "\n".join(directives), "sampling": sampling, "styles": tuple(names)}


_BOILERPLATE_PREFIXES = (
    re.compile(r"^\s*(?:hi|hello|hey)[,!\s]+(?:there[,!\s]+)?", re.IGNORECASE),
    re.compile(r"^\s*(?:certainly|absolutely|of course|sure thing)[,!\s]+", re.IGNORECASE),
    re.compile(r"^\s*(?:great question|good question|thanks for asking)[.!\s]*", re.IGNORECASE),
    re.compile(r"^\s*(?:as an ai(?: language model)?|as a language model)[,!:\s]+", re.IGNORECASE),
    re.compile(r"^\s*(?:i(?:'m| am) sorry[,!\s]+(?:but\s+)?)", re.IGNORECASE),
)


_SEPARATOR_LINE = re.compile(r"^\s*(?:[=\-_*~•·—–]\s*){3,}$")
_TRAILING_ELLIPSIS = re.compile(r"(?:\s*(?:\.{2,}|…))+\s*$")
_INLINE_EQUALS = re.compile(r"[ \t]+={1,}[ \t]+")


def clean_response(text: str | None) -> str:
    """Remove model chrome that reads badly aloud, then strip filler prefixes.

    Models like to close with ``...`` and separate sections with lines of ``=``,
    ``-`` or ``*``. Both look like a truncation in a character card and get read
    literally by speech synthesis. Drop separator-only lines and a trailing
    ellipsis, keep ordinary sentence periods, and leave URL query strings alone.
    """

    cleaned = (text or "").replace("\r\n", "\n").strip()
    lines: list[str] = []
    for line in cleaned.split("\n"):
        if _SEPARATOR_LINE.match(line):
            continue
        lines.append(_INLINE_EQUALS.sub(" — ", line).rstrip())
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"^\s*={2,}\s*", "", cleaned)
    cleaned = re.sub(r"\s*={2,}\s*$", "", cleaned)
    cleaned = _TRAILING_ELLIPSIS.sub("", cleaned).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    while cleaned:
        previous = cleaned
        for pattern in _BOILERPLATE_PREFIXES:
            cleaned = pattern.sub("", cleaned, count=1).lstrip(" \t\r\n,:;—-.")
            if cleaned != previous:
                break
        if cleaned == previous:
            break
    return _TRAILING_ELLIPSIS.sub("", cleaned).strip()
