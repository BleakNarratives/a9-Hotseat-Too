from __future__ import annotations


def _load_dotenv() -> None:
    import os
    from pathlib import Path as _P
    for candidate in (_P(".env"), _P(__file__).resolve().parent.parent / ".env"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break

_load_dotenv()

"""Small unified chat-completion client for local and hosted providers.

Provider credentials are resolved only when selection requires them. The module
uses the standard library transport, so a local-first install does not need an
extra HTTP package merely to import Hotseat.

A ``demo`` provider is included for frontends, docs, and tests: it composes
case-specific text from the pitch and any scout evidence in the prompt, never
touches the network, and labels every reply, so a UI can be built before any key
exists.
"""


import json
import logging
import os
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """A concise, user-safe provider selection or request failure.

    ``retryable`` means another key, model, or provider might survive. A short
    ``cooldown_seconds`` is different from ``exhausted``: a rate-limited key can
    come back after its window, while a daily/billing limit should be skipped
    for the rest of the session. The key itself is never included in the text.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
        kind: str = "unknown",
        cooldown_seconds: float | None = None,
        exhausted: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind
        self.cooldown_seconds = cooldown_seconds
        self.exhausted = exhausted
        if retryable is None:
            retryable = status_code in {400, 401, 402, 403, 404, 408, 409, 422, 425, 429} or (
                isinstance(status_code, int) and status_code >= 500
            )
        self.retryable = bool(retryable)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    credential_names: tuple[str, ...] = ()
    default_model: str = ""
    protocol: str = "openai"
    needs_key: bool = False



def _autoload_concierge_vault() -> None:
    import json, os
    from pathlib import Path as _P
    for vp in (_P.home() / ".concierge" / "vault.json", _P.home() / ".concierge" / "vault.v3.json"):
        if vp.exists():
            try:
                raw = json.loads(vp.read_text(encoding="utf-8"))
                merged = dict(raw) if isinstance(raw, dict) else {}
                if isinstance(merged.get("keys"), dict):
                    merged.update(merged["keys"])
                aliases = {
                    "GEMINI_API_KEY": ("GEMINI_API_KEY", "gemini_api_key", "gemini", "GOOGLE_API_KEY"),
                    "OPENROUTER_API_KEY": ("OPENROUTER_API_KEY", "openrouter_api_key", "openrouter"),
                    "XAI_API_KEY": ("XAI_API_KEY", "GROK_API_KEY", "xai", "grok"),
                    "GROQ_API_KEY": ("GROQ_API_KEY", "groq"),
                    "DEEPSEEK_API_KEY": ("DEEPSEEK_API_KEY", "deepseek"),
                    "CEREBRAS_API_KEY": ("CEREBRAS_API_KEY", "cerebras"),
                }
                for target, keys in aliases.items():
                    if not os.environ.get(target):
                        for k in keys:
                            v = merged.get(k)
                            if isinstance(v, str) and v.strip():
                                os.environ[target] = v.strip()
                                break
            except Exception:
                pass

_autoload_concierge_vault()

PROVIDERS: dict[str, ProviderSpec] = {
    "9router": ProviderSpec(
        "9router", "http://127.0.0.1:20128/v1", ("NINEROUTER_API_KEY",), "openai/gpt-4o-mini"
    ),
    "ai_gateway": ProviderSpec(
        "ai_gateway", "http://127.0.0.1:7071/v1", ("AI_GATEWAY_API_KEY",), "openai/gpt-4o-mini"
    ),
    "xai": ProviderSpec(
        "xai",
        "https://api.x.ai/v1",
        ("XAI_API_KEY", "GROK_API_KEY"),
        "grok-3-mini",
        needs_key=True,
    ),
    "groq": ProviderSpec(
        "groq",
        "https://api.groq.com/openai/v1",
        ("GROQ_API_KEY",),
        "openai/gpt-oss-120b",
        needs_key=True,
    ),
    "deepseek": ProviderSpec(
        "deepseek",
        "https://api.deepseek.com/v1",
        ("DEEPSEEK_API_KEY",),
        "deepseek-chat",
        needs_key=True,
    ),
    "cerebras": ProviderSpec(
        "cerebras",
        "https://api.cerebras.ai/v1",
        ("CEREBRAS_API_KEY",),
        "gpt-oss-120b",
        needs_key=True,
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "https://openrouter.ai/api/v1",
        ("OPENROUTER_API_KEY", "OPENROUTER_KEY"),
        "openai/gpt-4o-mini",
        needs_key=True,
    ),
    "openai": ProviderSpec(
        "openai", "https://api.openai.com/v1", ("OPENAI_API_KEY",), "gpt-4o-mini", needs_key=True
    ),
    "gemini": ProviderSpec(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        ("GEMINI_API_KEY",),
        "gemini-3.5-flash-lite",
        needs_key=True,
    ),
    "anthropic": ProviderSpec(
        "anthropic", "https://api.anthropic.com/v1", ("ANTHROPIC_API_KEY",), "claude-3-5-haiku-latest", "anthropic", True
    ),
    "mistral": ProviderSpec(
        "mistral", "https://api.mistral.ai/v1", ("MISTRAL_API_KEY",), "mistral-small-latest", needs_key=True
    ),
    "fireworks": ProviderSpec(
        "fireworks",
        "https://api.fireworks.ai/inference/v1",
        ("FIREWORKS_API_KEY",),
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        needs_key=True,
    ),
    "zen": ProviderSpec(
        "zen",
        "https://opencode.ai/zen/v1",
        ("OPENCODE_API_KEY", "OPENCODE_ZEN_API_KEY", "ZEN_API_KEY"),
        "deepseek-v4-flash-free",
        needs_key=True,
    ),
    "custom": ProviderSpec(
        "custom", "", ("CUSTOM_API_KEY", "BYOK_API_KEY"), "", needs_key=True
    ),
    "ollama": ProviderSpec(
        "ollama", "http://127.0.0.1:11434", (), "llama3.2:1b", "ollama", False
    ),
    "demo": ProviderSpec("demo", "", (), "hotseat-demo", "demo", False),
}

# Preference order for auto mode and fallback. Gemini and custom sit last:
# an invalid Google key should not stop the chain before working keys, and a
# custom endpoint is opt-in. An explicit --provider still selects either first.
_CLOUD_ORDER = (
    "openrouter",
    "openai",
    "xai",
    "deepseek",
    "mistral",
    "cerebras",
    "groq",
    "fireworks",
    "anthropic",
    "zen",
    "gemini",
    "custom",
)

PROVIDER_USER_AGENT = (
    "Hotseat/0.2 (+https://github.com/BleakNarratives/a9-Hotseat-Too)"
)
_DEFAULT_MAX_TOKENS = 1024

# Models often put ===, ----, or *** on their own line as section chrome.
# Speech synthesis reads those literally, so drop the whole line. Only an
# equals sign surrounded by whitespace is rewritten; URL query strings survive.
_SEPARATOR_LINE = re.compile(r"^\s*(?:[=\-_*~•·—–]\s*){3,}$")
_TRAILING_ELLIPSIS = re.compile(r"(?:\s*(?:\.{2,}|…))+\s*$")
_INLINE_EQUALS = re.compile(r"[ \t]+={1,}[ \t]+")

_CASE_RE = re.compile(r"The case on the table:\s*(.+?)\n", re.S)
_SEED_RE = re.compile(r"Seed idea:\s*(.+?)\.\s*Constraints:", re.S)
_SEED_SHORT_RE = re.compile(r"Seed:\s*(.+?)\.\s", re.S)
_CONTENDER_RE = re.compile(r"CONTENDER 0 — (.+?)\.\s", re.S)
_CONSTRAINTS_RE = re.compile(r"Constraints:\s*(.+?)(?:\n|$)", re.S)
_ANCHOR_RE = re.compile(
    r"^- ([^|\n]+?) \| ([^|\n]+?) \| ([^|\n]+?) \| (\$[^|\n]+?) \| ([^|\n]+?)(?: \||$)",
    re.M,
)
_SIGNAL_RE = re.compile(
    r"^- \[([^|\]]+?) \| [^|\n]+? \| weight [\d.]+\] (.+?)(?:\s+—\s+|$)", re.M
)
_PRICE_RE = re.compile(
    r"^- PRICE \[([^|\]]+?) \| [^|\n]+? \| weight [\d.]+\] (.+?): (\$[^\s(]+)", re.M
)

_ROLES = (
    ("producer", ("You are the Producer",)),
    ("critic", ("You are the Critic",)),
    ("foreman", ("You are the Foreman",)),
    ("architect", ("Turn the winning contender", "Design the vertical slice")),
    ("coroner", ("You are the Coroner",)),
    ("analyst", ("You are the Analyst",)),
    ("pm", ("You are the PM",)),
    ("builder", ("You are the Builder",)),
    ("qa", ("You are QA",)),
    ("adversary", ("You are The Adversary",)),
    ("reason", ("The Voice of Reason",)),
    ("whistleblower", ("The Whistleblower",)),
    ("evangelist", ("The Evangelist",)),
    ("fixer", ("You are The Fixer",)),
    ("audrey", ("Dame Audrey",)),
    ("claib", ("Claiborne",)),
    ("vertical", ("You are Vertical AI",)),
    ("marlowe", ("You are Marlowe",)),
    ("priya", ("You are Priya",)),
    ("zero", ("You are Zero",)),
    ("skeptic", ("ruthless skeptics",)),
    ("volunteer", ("volunteer defending",)),
)

def _clean_topic(text: str, limit: int = 150) -> str:
    text = re.sub(r"\s+", " ", text or "").strip().strip("'\"")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return text or "the idea"


_SLUG_STOP = {
    "a", "an", "the", "my", "our", "your", "this", "that", "for", "to", "of",
    "into", "and", "or", "with", "from",
}


def _slug(topic: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if w not in _SLUG_STOP]
    return "-".join(words[:3]) or "slice"


def _demo_context(system: str | None, messages: list[Mapping[str, str]]) -> dict[str, Any]:
    haystack = "\n".join(
        [system or ""] + [str(message.get("content", "")) for message in messages]
    )
    case = _CASE_RE.search(haystack)
    seed = _SEED_RE.search(haystack) or _SEED_SHORT_RE.search(haystack)
    if case:
        topic = _clean_topic(case.group(1).rstrip("."))
    elif seed:
        topic = _clean_topic(seed.group(1))
    else:
        contender = _CONTENDER_RE.search(haystack)
        first = next(
            (str(m.get("content", "")) for m in messages if m.get("role") == "user"), ""
        )
        raw = contender.group(1) if contender else first.split("\n", 1)[0]
        topic = _clean_topic(re.sub(r"^(topic|the idea|idea):\s*", "", raw, flags=re.I))

    constraints = _CONSTRAINTS_RE.search(haystack)
    anchors = [
        {
            "competitor": match.group(1).strip(),
            "price": match.group(4).strip(),
            "product": match.group(5).strip(),
        }
        for match in _ANCHOR_RE.finditer(haystack)
    ]
    signals = [
        {"source": match.group(1).strip(), "title": _clean_topic(match.group(2), 90)}
        for match in _SIGNAL_RE.finditer(haystack)
    ]
    prices = [
        {"competitor": match.group(1).strip(), "price": match.group(3).strip()}
        for match in _PRICE_RE.finditer(haystack)
    ]
    if not anchors and prices:
        anchors = [
            {"competitor": price["competitor"], "price": price["price"], "product": ""}
            for price in prices
        ]

    anchor = anchors[0] if anchors else None
    signal = signals[0] if signals else None
    if anchor:
        evidence = f"{anchor['competitor']} already lists {anchor['price']}."
        price_line = f"{anchor['competitor']} is at {anchor['price']}"
    elif signal:
        evidence = f"{signal['source']} is reporting “{signal['title']}”."
        price_line = "no price anchor on the wire, so test two prices before building"
    else:
        evidence = "The wire is quiet for this case, which is itself a finding."
        price_line = "no price anchor on the wire, so test two prices before building"

    return {
        "topic": topic,
        "slug": _slug(topic),
        "constraints": _clean_topic(constraints.group(1), 120) if constraints else "none given",
        "anchors": anchors,
        "signals": signals,
        "anchor": anchor,
        "signal": signal,
        "evidence": evidence,
        "price_line": price_line,
        "counts": (
            f"{len(signals)} signal{'s' if len(signals) != 1 else ''}, "
            f"{len(anchors)} price point{'s' if len(anchors) != 1 else ''}"
        ),
    }


def _detect_role(system: str) -> str:
    for role, needles in _ROLES:
        if any(needle in system for needle in needles):
            return role
    return "panel"


def _demo_turn(role: str, system: str, ctx: Mapping[str, Any]) -> str:
    topic = ctx["topic"]
    slug = ctx["slug"]
    evidence = ctx["evidence"]
    price_line = ctx["price_line"]
    bmad = "Design the vertical slice" in system

    if role == "producer":
        under = "the incumbent's price minus a third" if ctx["anchor"] else "$9"
        premium = "ten times the incumbent" if ctx["anchor"] else "$500/mo"
        return (
            f"CONTENDER 0 — {topic}. Customer: whoever is already solving this by hand. "
            f"Price: {price_line}. First ten: the people who complained about it publicly. "
            f"Dies on: nobody paying twice.\n"
            f"CONTENDER 1 — THE CHEAP ONE: one job, one screen, {under}. Wedge: no setup. "
            f"First ten: one community thread. Dies on: no support loop.\n"
            f"CONTENDER 2 — THE PREMIUM ONE: done for you at {premium}. Wedge: white glove. "
            f"First ten: warm intros. Dies on: your calendar.\n"
            f"CONTENDER 3 — THE NICHE WEDGE: {topic}, only for one trade. Wedge: pre-filled answers. "
            f"First ten: one trade group. Dies on: a market too small to pay.\n"
            f"Wire: {evidence}"
        )
    if role == "critic":
        return (
            f"“{topic}” rests on one unmeasured claim: that the pain is frequent enough to pay for. "
            f"{evidence} The cheap contender has no support loop, the premium one is your calendar, "
            f"and the niche wedge needs a group you are not in. None of the four shows a second payment."
        )
    if role == "foreman":
        winner = (
            f"the niche wedge that undercuts {ctx['anchor']['competitor']}"
            if ctx["anchor"]
            else "the cheap one"
        )
        return (
            f"Winner: {winner}. Deciding difference: it can name its first ten buyers this week. "
            f"Eliminated: the seed — it is a feature looking for a buyer. "
            f"Ranking: {winner}, premium, cheap, the seed."
        )
    if role == "architect":
        if bmad:
            return (
                f"Slice: `{slug}` end to end. Interfaces: `parse(text) -> Case`, "
                f"`run(case) -> Brief`. Storage: SQLite. Risky dependency: model output discipline. "
                f"Defer: accounts, sync, scheduling."
            )
        return (
            f"Slice: one path through “{topic}”. Files: `hotseat_core/{slug}.py`, "
            f"`tests/test_{slug}.py`. First story: a user submits the case and gets a decision "
            f"plus one next action. Interface: `run(case: str) -> str`. Timebox: one session. "
            f"Defer: history, accounts, exports."
        )
    if role == "coroner":
        cause = (
            "distribution, not quality"
            if not ctx["anchor"]
            else f"pricing against {ctx['anchor']['competitor']}"
        )
        return (
            f"“{topic}” died of {cause}. {evidence} The smallest change that would have saved it: "
            f"pick one buyer, one repeated job, and sell the output before the build. "
            f"The winner's remaining risk: the niche is real but small."
        )
    if role == "analyst":
        return (
            f"User: someone already doing “{topic}” by hand, badly. Evidence on file: {ctx['counts']}. "
            f"The assumption that kills it: they will change a habit for a tool. "
            f"Constraint on record: {ctx['constraints']}."
        )
    if role == "pm":
        return (
            f"Product: “{topic}”, in one command. Must-haves: capture the case, force one decision, "
            f"emit one next action. Non-goals: accounts, sync, a mobile app. "
            f"Metric: case to decision under a minute. Slice: `{slug}` prints the result."
        )
    if role == "builder":
        return (
            f"Files: `hotseat_core/{slug}.py`, `tests/test_{slug}.py`. "
            f"Interface: `run(case: str) -> str`. First test: a one-line case returns a non-empty "
            f"decision. Timebox: one session. Done today: it runs on a sample case."
        )
    if role == "qa":
        return (
            f"Acceptance: `{slug}` returns one decision and one next action; no invented evidence; "
            f"output is valid Markdown. Kill criteria: it needs a cloud key, or it fabricates a price. "
            f"Cut: history. GO — the slice is one session and the risk is testable."
        )
    if role == "adversary":
        return f"“{topic}” fails on ownership. Nobody in the plan owns the boring middle. {evidence}"
    if role == "reason":
        return (
            f"The evidence supports a two-week test of “{topic}”, not a launch. "
            f"{evidence} Ten real uses will tell you more than another month of planning."
        )
    if role == "whistleblower":
        return (
            f"The thing nobody is saying about “{topic}”: it is a feature, not a product, and the "
            f"room already knows it. {evidence} Say it while it is still cheap."
        )
    if role == "evangelist":
        return (
            f"The case for “{topic}”: it lets one person do work that used to take a team. "
            f"The blind spot: that person is the buyer, the user, and the support line. {evidence}"
        )
    if role == "fixer":
        return (
            f"1. Name one owner for “{topic}”. 2. Ship the smallest version this week. "
            f"3. Log ten uses and review them in fourteen days. Evidence to watch: {evidence}"
        )
    if role == "audrey":
        return (
            f"“{topic}” assumes the hard part is the build. It is the Tuesday after. {evidence} "
            f"Decide who owns it then, or stop calling it a product."
        )
    if role == "claib":
        return (
            f"“{topic}” solves the visible problem. The one underneath is distribution. "
            f"{evidence} Fix the front door before you add another room."
        )
    if role == "vertical":
        return f"Ship the smallest version of “{topic}” this week. {evidence} Stop planning."
    if role == "marlowe":
        return (
            f"You already know what is wrong with “{topic}”. You are here hoping someone says it "
            f"is not that bad. {evidence} So — what are we doing about it?"
        )
    if role == "priya":
        return (
            f"Strip the feeling out of “{topic}”. Which behavior repeats? That loop is the product. "
            f"Everything downstream is a symptom."
        )
    if role == "zero":
        return (
            f"“{topic}” is not the real question. What are you avoiding by building it? "
            f"Answer that before the next session."
        )
    if role == "skeptic":
        return (
            f"“{topic}” leans on one unmeasured number: that people come back after week two. "
            f"{evidence} Nothing here tests retention, and the cost model ignores support."
        )
    if role == "volunteer":
        return (
            f"Fair hit on retention. It is the cheapest thing to fix: run ten sessions of "
            f"“{topic}” and log who returns. If two do, it survives; if none do, you learned it "
            f"for a weekend."
        )
    return f"“{topic}” needs one owner, one test, and one price. Evidence: {evidence}"


def demo_response(system: str | None, messages: list[Mapping[str, str]]) -> str:
    """Return a deterministic, case- and evidence-aware stand-in reply."""

    system_text = system or ""
    ctx = _demo_context(system, messages)
    return _demo_turn(_detect_role(system_text), system_text, ctx).strip()


def _get_secret(key: str, secret_loader: Callable[[str, str], str] | None = None) -> str:
    """Call the repository's vault_loader lazily; environment overrides remain first."""

    if os.environ.get(key):
        return os.environ[key]
    try:
        if secret_loader is None:
            # Delayed import means missing vaults/keys never break module import.
            from .vault_loader import get_secret

            secret_loader = get_secret
        return str(secret_loader(key, "") or "")
    except (ImportError, OSError, ValueError):
        return ""


def _provider_url(spec: ProviderSpec) -> str:
    for suffix in ("BASE_URL", "ENDPOINT", "URL"):
        override = os.environ.get(f"{spec.name.upper()}_{suffix}", "").strip()
        if override:
            return override.rstrip("/")
    if not spec.base_url:
        raise ProviderError(
            f"Provider '{spec.name}' needs an endpoint. Set "
            f"{spec.name.upper()}_BASE_URL to an OpenAI-compatible /v1 URL."
        )
    return spec.base_url.rstrip("/")


def _duration_seconds(value: str | None) -> float | None:
    """Parse Retry-After's seconds/date and common rate-limit reset formats."""

    if not value:
        return None
    raw = str(value).strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        when = None
    if when is not None:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    total = 0.0
    units = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([smhd])", raw.lower()):
        total += float(amount) * units[unit]
    return total or None


def _retry_after_seconds(headers: Any) -> float | None:
    """Read the first usable retry hint from an HTTP error response."""

    if headers is None:
        return None
    for name in (
        "Retry-After",
        "retry-after",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset",
    ):
        value = headers.get(name)
        seconds = _duration_seconds(value)
        if seconds is not None:
            return seconds
    return None


def _looks_like_daily_limit(detail: str) -> bool:
    text = (detail or "").lower()
    return any(
        marker in text
        for marker in (
            "daily",
            "per day",
            "per-day",
            "today",
            "24 hour",
            "24-hour",
            "day limit",
            "insufficient_quota",
            "billing",
            "credit",
            "budget",
            "monthly",
            "subscription",
            "quota exceeded",
        )
    )


def _looks_like_model_failure(detail: str) -> bool:
    text = (detail or "").lower()
    return any(
        marker in text
        for marker in (
            "model",
            "context length",
            "maximum context",
            "too many tokens",
            "unsupported",
            "does not exist",
            "not found",
            "no such",
        )
    )


def _http_failure(provider: str, exc: HTTPError, detail: str) -> ProviderError:
    """Turn one HTTP status into an actionable, secret-free failure."""

    code = int(exc.code)
    headers = getattr(exc, "headers", None)
    reset = _retry_after_seconds(headers)
    suffix = f": {detail}" if detail else ""
    hint = ""
    if code == 429:
        if _looks_like_daily_limit(detail):
            kind, cooldown, exhausted, hint = "daily_limit", None, True, " (daily limit)"
        else:
            kind, cooldown, exhausted = "cooldown", reset or 30.0, False
            hint = f" (cooldown {int(cooldown)}s)"
    elif code in {401, 403}:
        kind, cooldown, exhausted = "auth", reset, False
        hint = " (credential rejected; trying the next key)"
    elif code == 402:
        kind, cooldown, exhausted = "billing", None, True
        hint = " (billing/credit exhausted)"
    elif code in {400, 404, 422}:
        kind = "model" if _looks_like_model_failure(detail) else "bad_request"
        cooldown, exhausted = None, False
    elif code in {408, 409, 425} or code >= 500:
        kind, cooldown, exhausted = "server", reset or 5.0, False
        hint = f" (retry in {int(cooldown)}s)"
    else:
        kind, cooldown, exhausted = "http", None, False
    return ProviderError(
        f"Provider '{provider}' returned HTTP {code}{suffix}.{hint}",
        status_code=code,
        kind=kind,
        cooldown_seconds=cooldown,
        exhausted=exhausted,
        retryable=code in {400, 401, 402, 403, 404, 408, 409, 422, 425, 429}
        or code >= 500,
    )


def probe_9router(timeout: float = 0.25, *, host: str = "127.0.0.1", port: int = 20128) -> bool:
    """Fast TCP health check; a reachable listener is enough to select it."""

    try:
        with socket.create_connection((host, port), timeout=max(0.01, timeout)):
            return True
    except OSError:
        return False


def _split_key_values(raw: str) -> list[str]:
    """Allow one env var to hold a comma/newline-separated BYOK key ring."""

    return [part.strip() for part in re.split(r"[\n,;]+", raw or "") if part.strip()]


def _credential_pool(
    spec: ProviderSpec,
    secret_loader: Callable[[str, str], str] | None = None,
) -> list[str]:
    """Resolve every key for a provider without ever logging a value.

    Supports ``PROVIDER_API_KEY``, ``PROVIDER_API_KEY_2`` ... and the plural
    ``PROVIDER_KEYS`` form. Each value may itself be comma-separated, which makes
    a free-tier key ring easy to keep in one environment variable.
    """

    values: list[str] = []
    seen: set[str] = set()
    for key_name in spec.credential_names:
        candidates = [key_name]
        candidates.extend(f"{key_name}_{slot}" for slot in range(2, 10))
        base = re.sub(r"(_API)?_KEY$", "", key_name)
        candidates.extend((f"{base}_KEYS", f"{base}_API_KEYS"))
        for candidate in candidates:
            raw = _get_secret(candidate, secret_loader)
            for value in _split_key_values(raw):
                if value not in seen:
                    seen.add(value)
                    values.append(value)
    return values


def _provider_usable(spec: ProviderSpec) -> bool:
    try:
        _provider_url(spec)
    except ProviderError:
        return False
    return True


def _configured_cloud_provider(
    secret_loader: Callable[[str, str], str] | None = None,
) -> tuple[str, str] | None:
    for name in _CLOUD_ORDER:
        spec = PROVIDERS[name]
        if not _provider_usable(spec):
            continue
        pool = _credential_pool(spec, secret_loader)
        if pool:
            return name, pool[0]
    return None


def _configured_cloud_names(
    secret_loader: Callable[[str, str], str] | None = None,
) -> list[str]:
    """Provider names with a discoverable key, in deterministic order."""

    names: list[str] = []
    for name in _CLOUD_ORDER:
        spec = PROVIDERS[name]
        if _provider_usable(spec) and _credential_pool(spec, secret_loader):
            names.append(name)
    return names


def configured_providers(
    secret_loader: Callable[[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Return provider readiness without exposing any credential value.

    Keyed providers are ``configured`` only when a credential resolves from the
    environment, repo ``.env``, or the Concierge vault. Local and demo providers
    need no key and are always marked configured; reachability is a separate
    question and is deliberately not probed here. ``key_count`` is safe to show:
    it says a key ring exists without identifying any key.
    """

    rows: list[dict[str, Any]] = []
    for name, spec in PROVIDERS.items():
        pool = _credential_pool(spec, secret_loader) if spec.needs_key else []
        has_key = bool(pool)
        usable = _provider_usable(spec)
        rows.append(
            {
                "name": name,
                "configured": (not spec.needs_key) or (has_key and usable),
                "requires_key": spec.needs_key,
                "has_credential": has_key,
                "key_count": len(pool),
                "endpoint_configured": usable,
                "credential_names": list(spec.credential_names),
                "local": name in {"9router", "ai_gateway", "ollama"},
                "offline": name == "demo",
                "default_model": spec.default_model,
            }
        )
    return rows


class FallbackClient:
    """Try keys, models, and providers in order until one answers.

    A short rate limit puts that key to sleep for its cooldown; a daily or
    billing limit puts it away for the rest of the session. Auth/model failures
    move on immediately. The successful provider, key slot, and model remain on
    the wrapper so the runtime can show exactly who answered.
    """

    def __init__(self, clients: list[Any]) -> None:
        if not clients:
            raise ProviderError("No provider clients were supplied.")
        self.clients = list(clients)
        self.index = 0
        self.provider = str(getattr(self.clients[0], "provider", "unknown"))
        self.key_label = str(getattr(self.clients[0], "key_label", "key 1"))
        self.model: str | None = None
        self.fallback_used = False
        self.last_error: str | None = None
        self.attempts: list[str] = []
        self._initial_provider = self.provider

    def _activate(self, index: int, model: str | None = None) -> None:
        # Advance to the next key/provider on the following turn. This spreads
        # load across the ring instead of pinning every turn to the first key
        # that happened to answer.
        self.index = (index + 1) % len(self.clients)
        client = self.clients[index]
        self.provider = str(getattr(client, "provider", "unknown"))
        self.key_label = str(getattr(client, "key_label", "key 1"))
        self.model = model or getattr(client, "last_model", None)

    def _label(self, client: Any, model: str | None) -> str:
        provider = str(getattr(client, "provider", "unknown"))
        key = str(getattr(client, "key_label", "key 1"))
        return f"{provider} {key}" + (f" / {model}" if model else "")

    @staticmethod
    def _available(client: Any) -> bool:
        check = getattr(client, "available", None)
        return bool(check()) if callable(check) else True

    def _models_for(self, client: Any, requested: str | None) -> list[str | None]:
        # A model named for the primary provider is not portable. Backups use
        # their own configured default (and optional fallback model list).
        same_provider = str(getattr(client, "provider", "")) == self._initial_provider
        default = getattr(client, "default_model", None)
        default_name: str | None = None
        if callable(default):
            try:
                default_name = default()
            except ProviderError:
                default_name = None
        primary = requested if same_provider else None
        models: list[str | None] = []
        if primary:
            models.append(primary)
        if default_name and default_name not in models:
            models.append(default_name)
        if not models:
            models.append(None)
        fallback = getattr(client, "fallback_models", None)
        if callable(fallback):
            try:
                candidates = fallback()
            except ProviderError:
                candidates = ()
            for name in candidates:
                if name and name not in models:
                    models.append(name)
        return models

    @property
    def fallback_trail(self) -> list[str]:
        return list(self.attempts)

    def complete(self, **kwargs: Any) -> str:
        last: ProviderError | None = None
        self.attempts.clear()
        on_chunk = kwargs.get("on_chunk")
        # If a provider dies halfway through a stream, switching providers would
        # append a second answer to the partial one. Buffer the fallback chain and
        # release only the winning stream; a single direct client still streams live.
        buffered: list[str] | None = [] if callable(on_chunk) and len(self.clients) > 1 else None
        order = list(range(self.index, len(self.clients))) + list(range(0, self.index))
        for index in order:
            client = self.clients[index]
            if not self._available(client):
                self.fallback_used = True
                self.attempts.append(self._label(client, None) + " skipped (cooling down)")
                continue
            for model in self._models_for(client, kwargs.get("model")):
                call = dict(kwargs)
                call["model"] = model
                if buffered is not None:
                    buffered.clear()
                    call["on_chunk"] = buffered.append
                label = self._label(client, model)
                try:
                    text = client.complete(**call)
                    self._activate(index, model)
                    if buffered is not None and callable(on_chunk):
                        for piece in buffered:
                            on_chunk(piece)
                    return text
                except ProviderError as exc:
                    last = exc
                    self.last_error = str(exc)
                    self.attempts.append(f"{label}: {exc}")
                    logger.warning(
                        "provider attempt failed provider=%s key=%s model=%s status=%s kind=%s",
                        getattr(client, "provider", "unknown"),
                        getattr(client, "key_label", "?"),
                        model or "default",
                        getattr(exc, "status_code", None),
                        getattr(exc, "kind", "unknown"),
                    )
                    if not getattr(exc, "retryable", False):
                        raise
                    self.fallback_used = True
                    # A key-level limit should move to the next key, not burn
                    # the same key on every fallback model. A model/bad-request
                    # failure is the one case worth trying another model.
                    if getattr(exc, "kind", "unknown") in {
                        "auth",
                        "cooldown",
                        "daily_limit",
                        "billing",
                        "server",
                    }:
                        break
        summary = "; ".join(self.attempts[-8:]) or "no configured key answered"
        logger.error("all provider attempts failed: %s", summary)
        raise ProviderError(
            f"All providers failed. {summary}",
            retryable=True,
            kind="all_failed",
        )


def build_client(
    provider: str = "auto",
    model: str | None = None,
    *,
    secret_loader: Callable[[str, str], str] | None = None,
    fallback: bool = True,
) -> Any:
    """Resolve the primary client and add credential-backed fallbacks."""

    primary = resolve_provider(provider, secret_loader=secret_loader)
    requested = str(getattr(primary, "provider", provider or "auto")).lower()
    if not fallback or requested == "demo":
        return primary

    clients: list[Any] = [primary]
    if requested in PROVIDERS:
        pool = _credential_pool(PROVIDERS[requested], secret_loader)
        for slot, key in enumerate(pool, start=1):
            if getattr(primary, "api_key", None) == key:
                continue
            try:
                clients.append(
                    ProviderClient(
                        requested,
                        api_key=key,
                        key_slot=slot,
                        secret_loader=secret_loader,
                    )
                )
            except ProviderError:
                continue
    for name in _configured_cloud_names(secret_loader):
        if name == requested:
            continue
        for slot, key in enumerate(_credential_pool(PROVIDERS[name], secret_loader), start=1):
            try:
                clients.append(
                    ProviderClient(
                        name,
                        api_key=key,
                        key_slot=slot,
                        secret_loader=secret_loader,
                    )
                )
            except ProviderError:
                continue
    return FallbackClient(clients) if len(clients) > 1 else primary


def resolve_provider(
    provider: str = "auto",
    *,
    secret_loader: Callable[[str, str], str] | None = None,
    health_probe: Callable[[], bool] = probe_9router,
) -> "ProviderClient":
    """Resolve an explicit provider, or probe local 9router first in auto mode.

    In auto mode, when 9router is not listening, configured cloud credentials are
    checked in a deterministic order. If none are available, the demo provider
    keeps the room open with in-character prose. No credential is loaded for an
    unselected explicit provider.
    """

    requested = (provider or "auto").strip().lower()
    if requested == "auto":
        if health_probe():
            return ProviderClient("9router", secret_loader=secret_loader)
        cloud = _configured_cloud_provider(secret_loader)
        if cloud:
            name, key = cloud
            return ProviderClient(name, api_key=key, secret_loader=secret_loader)
        # A room with no keys should still open with in-character demo prose
        # rather than a credential error. The warning stays in the server log.
        logger.warning("No cloud provider credential found; using the demo provider.")
        return ProviderClient("demo", secret_loader=secret_loader)

    if requested not in PROVIDERS and requested != "ai-gateway":
        choices = ", ".join(("auto", *PROVIDERS.keys()))
        raise ProviderError(f"Unknown provider '{provider}'. Choose one of: {choices}.")
    if requested == "ai-gateway":
        requested = "ai_gateway"
    return ProviderClient(requested, secret_loader=secret_loader)


@dataclass
class ProviderClient:
    """Resolved provider plus retrying request implementation."""

    provider: str
    api_key: str | None = None
    timeout: float = 30.0
    retries: int = 1
    key_slot: int = 1
    key_label: str = ""
    secret_loader: Callable[[str, str], str] | None = field(default=None, repr=False)
    spec: ProviderSpec = field(init=False, repr=False)
    base_url: str = field(init=False, repr=False)
    cooldown_until: float = field(default=0.0, init=False)
    exhausted_until: float = field(default=0.0, init=False)
    last_model: str | None = field(default=None, init=False)
    last_error: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ProviderError(f"Unknown provider '{self.provider}'.")
        self.spec = PROVIDERS[self.provider]
        self.base_url = "" if self.spec.protocol == "demo" else _provider_url(self.spec)
        if self.spec.needs_key:
            self.key_label = self.key_label or f"key {self.key_slot}"
        if self.api_key is None and self.spec.needs_key:
            self.api_key = self._load_selected_key()

    def _load_selected_key(self) -> str:
        pool = _credential_pool(self.spec, self.secret_loader)
        if pool:
            return pool[0]
        raise ProviderError(
            f"Provider '{self.provider}' requires a credential. Set "
            f"{' or '.join(self.spec.credential_names)} in the environment or ~/.concierge/vault.json."
        )

    def available(self) -> bool:
        """False while a key is cooling down or has spent a daily budget."""

        return time.time() >= max(self.cooldown_until, self.exhausted_until)

    def default_model(self) -> str:
        model = (
            os.environ.get(f"{self.provider.upper()}_MODEL", "").strip()
            or self.spec.default_model
        )
        if not model:
            raise ProviderError(
                f"Provider '{self.provider}' needs a model. Set "
                f"{self.provider.upper()}_MODEL for this endpoint.",
                retryable=True,
                kind="model",
            )
        return model

    def fallback_models(self) -> tuple[str, ...]:
        raw = os.environ.get(f"{self.provider.upper()}_FALLBACK_MODELS", "")
        primary = os.environ.get(f"{self.provider.upper()}_MODEL", "") or self.spec.default_model
        return tuple(
            model.strip()
            for model in raw.split(",")
            if model.strip() and model.strip() != primary
        )

    def _record_failure(self, exc: ProviderError) -> None:
        self.last_error = str(exc)
        now = time.time()
        if exc.status_code in {401, 403} and not exc.cooldown_seconds:
            # A bad or unauthorized key should not be touched again this session.
            self.cooldown_until = now + 3600
        elif exc.cooldown_seconds:
            self.cooldown_until = now + max(1.0, float(exc.cooldown_seconds))
        if exc.exhausted:
            self.exhausted_until = now + 86400

    # ── public API ────────────────────────────────────────────────────────────
    def complete(
        self,
        *,
        messages: list[Mapping[str, str]],
        model: str | None = None,
        system: str | None = None,
        sampling: Mapping[str, Any] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """Return assistant text from a messages-style chat request.

        When ``on_chunk`` is supplied and the protocol supports streaming, text is
        delivered incrementally as it arrives. Anthropic falls back to a single
        chunk so callers get one consistent contract.
        """

        selected_model = model or self.default_model()
        options = dict(sampling or {})

        if self.spec.protocol == "demo":
            text = demo_response(system, messages)
            self.last_model = selected_model
            if on_chunk:
                on_chunk(text)
            return text

        if on_chunk is None or self.spec.protocol == "anthropic":
            text = self._complete_once(messages, selected_model, system, options)
            self.last_model = selected_model
            if on_chunk:
                on_chunk(text)
            return text
        text = self._complete_stream(messages, selected_model, system, options, on_chunk)
        self.last_model = selected_model
        return text

    # ── request bodies ────────────────────────────────────────────────────────
    def _request_parts(
        self,
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
        *,
        stream: bool,
    ) -> tuple[dict[str, Any], str, dict[str, str]]:
        if self.spec.protocol == "anthropic":
            body = self._anthropic_body(messages, model, system, options)
            return body, "/messages", {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}
        if self.spec.protocol == "ollama":
            body = self._ollama_body(messages, model, system, options, stream=stream)
            return body, "/api/chat", {}
        body = self._openai_body(messages, model, system, options, stream=stream)
        return body, "/chat/completions", (
            {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )

    @staticmethod
    def _openai_body(
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        normalized = []
        if system:
            normalized.append({"role": "system", "content": system})
        normalized.extend(
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
        )
        body: dict[str, Any] = {"model": model, "messages": normalized}
        allowed = {"temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "stop"}
        body.update({key: value for key, value in options.items() if key in allowed and value is not None})
        # OpenRouter reserves credit for the full context window when max_tokens
        # is omitted, which can reject a valid request as unaffordable. A turn
        # is a short monologue; 1024 leaves room without the reservation.
        body.setdefault("max_tokens", _DEFAULT_MAX_TOKENS)
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _anthropic_body(
        messages: list[Mapping[str, str]], model: str, system: str | None, options: Mapping[str, Any]
    ) -> dict[str, Any]:
        normalized = [
            {"role": "assistant" if m.get("role") == "assistant" else "user", "content": str(m.get("content", ""))}
            for m in messages
            if m.get("role") != "system"
        ]
        body: dict[str, Any] = {
            "model": model,
            "messages": normalized,
            "max_tokens": int(options.get("max_tokens", 512)),
        }
        if system:
            body["system"] = system
        for key in ("temperature", "top_p", "stop_sequences"):
            if key in options:
                body[key] = options[key]
        return body

    @staticmethod
    def _ollama_body(
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        normalized = []
        if system:
            normalized.append({"role": "system", "content": system})
        normalized.extend(
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
        )
        ollama_options = {
            key: options[key]
            for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "num_predict")
            if key in options
        }
        if "max_tokens" in options:
            ollama_options["num_predict"] = options["max_tokens"]
        return {
            "model": model,
            "messages": normalized,
            "stream": stream,
            "options": ollama_options,
        }

    # ── transport ─────────────────────────────────────────────────────────────
    def _build_request(
        self,
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
        *,
        stream: bool,
    ) -> Request:
        body, path, headers = self._request_parts(messages, model, system, options, stream=stream)
        payload = json.dumps(body).encode("utf-8")
        return Request(
            self.base_url + path,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": PROVIDER_USER_AGENT,
                **headers,
            },
            method="POST",
        )

    def _complete_once(
        self,
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
    ) -> str:
        request = self._build_request(messages, model, system, options, stream=False)
        data = self._send(request)
        try:
            if self.spec.protocol == "anthropic":
                return "".join(
                    item.get("text", "") for item in data.get("content", []) if item.get("type") == "text"
                ).strip()
            if self.spec.protocol == "ollama":
                return str(data.get("message", {}).get("content", "")).strip()
            return str(data["choices"][0]["message"].get("content", "")).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Provider '{self.provider}' returned an unexpected response format.",
                retryable=True,
                kind="response",
            ) from exc

    def _complete_stream(
        self,
        messages: list[Mapping[str, str]],
        model: str,
        system: str | None,
        options: Mapping[str, Any],
        on_chunk: Callable[[str], None],
    ) -> str:
        request = self._build_request(messages, model, system, options, stream=True)
        chunks: list[str] = []
        try:
            with urlopen(request, timeout=max(0.1, float(self.timeout))) as response:
                for raw in response:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    piece = self._parse_stream_line(line)
                    if piece is None:
                        continue
                    if piece:
                        chunks.append(piece)
                        on_chunk(piece)
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            failure = _http_failure(self.provider, exc, detail)
            self._record_failure(failure)
            raise failure from None
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", None) or exc
            raise ProviderError(
                f"Could not reach provider '{self.provider}': {reason}.", retryable=True
            ) from None
        except ValueError as exc:
            raise ProviderError(
                f"Provider '{self.provider}' returned invalid stream data: {exc}.",
                retryable=True,
                kind="response",
            ) from None
        return "".join(chunks).strip()

    def _parse_stream_line(self, line: str) -> str | None:
        if self.spec.protocol == "ollama":
            data = json.loads(line)
            if not isinstance(data, dict):
                return None
            return str(data.get("message", {}).get("content") or data.get("response") or "")
        if line.startswith(":"):
            return None
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            return None
        data = json.loads(line)
        if not isinstance(data, dict):
            return None
        choices = data.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        return str(content) if content else ""

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str:
        try:
            error_data = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            return ""
        if isinstance(error_data, dict):
            error = error_data.get("error", {})
            if isinstance(error, dict):
                return str(error.get("message", ""))[:300]
            if error:
                return str(error)[:300]
        return ""

    def _send(self, request: Request) -> dict[str, Any]:
        attempts = max(0, int(self.retries)) + 1
        for attempt in range(attempts):
            try:
                with urlopen(request, timeout=max(0.1, float(self.timeout))) as response:
                    parsed = json.loads(response.read().decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise ProviderError(
                            f"Provider '{self.provider}' returned invalid JSON data.",
                            retryable=True,
                            kind="response",
                        )
                    return parsed
            except HTTPError as exc:
                # Only transient server errors are worth a quick same-key retry.
                # A rate limit must move to the next key immediately instead of
                # making the user wait through the cooldown.
                if attempt + 1 < attempts and exc.code >= 500:
                    time.sleep(min(0.2 * (2**attempt), 1.0))
                    continue
                detail = self._http_error_detail(exc)
                failure = _http_failure(self.provider, exc, detail)
                self._record_failure(failure)
                raise failure from None
            except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(0.2 * (2**attempt), 1.0))
                    continue
                reason = getattr(exc, "reason", None) or exc
                raise ProviderError(
                    f"Could not reach provider '{self.provider}': {reason}.", retryable=True
                ) from None
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProviderError(
                    f"Provider '{self.provider}' returned invalid JSON: {exc}.",
                    retryable=True,
                    kind="response",
                ) from None
        raise ProviderError(f"Provider '{self.provider}' request failed after retries.")


def available_providers() -> list[dict[str, Any]]:
    """Return provider metadata without probing services or loading credentials."""

    return [
        {
            "name": name,
            "local": name in {"9router", "ai_gateway", "ollama"},
            "offline": name == "demo",
            "requires_key": spec.needs_key,
            "default_model": spec.default_model,
        }
        for name, spec in PROVIDERS.items()
    ]
