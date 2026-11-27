"""Zero-dependency token compressor (TOON-style tabular encoder + turn compactor)."""

from __future__ import annotations
import re
from typing import Any

FILLER_RE = re.compile(
    r"\b(basically|literally|honestly|actually|you know|kind of|sort of|in order to)\b",
    re.IGNORECASE,
)


def to_toon(name: str, rows: list[dict[str, Any]]) -> str:
    """Encode uniform dict lists into header-driven TOON format to cut JSON punctuation tokens."""
    if not rows:
        return f"{name}[0]{{}}:"
    keys = list(rows[0].keys())
    header = f"{name}[{len(rows)}]{{{','.join(keys)}}}:"
    body = []
    for row in rows:
        vals = [str(row.get(k, "")).replace("\n", " ").replace(",", ";") for k in keys]
        body.append("  " + ",".join(vals))
    return "\n".join([header, *body])


def compact_prompt(text: str, max_chars: int = 1800) -> str:
    """Strip low-entropy filler words and collapse whitespace without breaking structure."""
    cleaned = FILLER_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > max_chars:
        head = cleaned[: int(max_chars * 0.7)]
        tail = cleaned[-int(max_chars * 0.25) :]
        return f"{head}\n...[compacted]...\n{tail}"
    return cleaned
