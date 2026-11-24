"""Small unified chat-completion client for local and hosted providers.

Provider credentials are resolved only when selection requires them. The module
uses the standard library transport, so a local-first install does not need an
extra HTTP package merely to import Hotseat.

A ``demo`` provider is included for frontends, docs, and tests: it returns fixed,
clearly labeled text without touching the network, so a UI can be built before
any key exists.
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """A concise, user-safe provider selection or request failure."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    credential_names: tuple[str, ...] = ()
    default_model: str = ""
    protocol: str = "openai"
    needs_key: bool = False


PROVIDERS: dict[str, ProviderSpec] = {
    "9router": ProviderSpec(
        "9router", "http://127.0.0.1:20128/v1", ("NINEROUTER_API_KEY",), "openai/gpt-4o-mini"
    ),
    "ai_gateway": ProviderSpec(
        "ai_gateway", "http://127.0.0.1:7071/v1", ("AI_GATEWAY_API_KEY",), "openai/gpt-4o-mini"
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "https://openrouter.ai/api/v1",
        ("OPENROUTER_API_KEY", "OPENROUTER_KEY"),
        "openai/gpt-4o-mini",
        needs_key=True,
    ),
    "anthropic": ProviderSpec(
        "anthropic", "https://api.anthropic.com/v1", ("ANTHROPIC_API_KEY",), "claude-3-5-haiku-latest", "anthropic", True
    ),
    "mistral": ProviderSpec(
        "mistral", "https://api.mistral.ai/v1", ("MISTRAL_API_KEY",), "mistral-small-latest", needs_key=True
    ),
    "cerebras": ProviderSpec(
        "cerebras", "https://api.cerebras.ai/v1", ("CEREBRAS_API_KEY",), "llama3.1-8b", needs_key=True
    ),
    "groq": ProviderSpec(
        "groq", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",), "llama-3.1-8b-instant", needs_key=True
    ),
    "ollama": ProviderSpec(
        "ollama", "http://127.0.0.1:11434", (), "llama3.2:1b", "ollama", False
    ),
    "demo": ProviderSpec("demo", "", (), "hotseat-demo", "demo", False),
}

_CLOUD_ORDER = ("openrouter", "anthropic", "mistral", "cerebras", "groq")

DEMO_LINES: tuple[tuple[str, str], ...] = (
    (
        "Dame Audrey",
        "I see. You want the version where nobody has to test it. Right then: this plan assumes the hard part is the code, when it is the maintenance. Decide who owns it on a rainy Tuesday, or stop calling it a product.",
    ),
    (
        "Claib",
        "Actually, you're solving the visible problem. The thing underneath it is distribution — nobody can find the thing you built. Fix the front door before you add another room.",
    ),
    (
        "Vertical AI",
        "The idea is sound. The timeline is the story you tell yourself to avoid starting. Pick the smallest version and ship it this week.",
    ),
    (
        "Skeptic",
        "The claim rests on one unmeasured number: that people will keep coming back after week two. Nothing here tests retention, and the cost model ignores support. Start with the weakest point, not the demo.",
    ),
    (
        "Volunteer",
        "Fair hit on retention. It is also the cheapest thing to fix: run ten sessions and log who returns. If two do, the idea survives; if none do, we learned it for a weekend instead of a quarter.",
    ),
    (
        "Marlowe",
        "You already know what is wrong. You are here because you want someone to tell you it is not as bad as you think. It is. But you have handled worse. So — what are we actually doing about it?",
    ),
    (
        "Priya",
        "Strip out the feeling for a second. What is the behavior that keeps repeating? That is the loop. It breaks at the point where you commit before you have decided, and every other problem downstream is a symptom.",
    ),
    (
        "Zero",
        "You are not afraid of failing. You are afraid of finding out what you will do if you succeed. Sit with that one.",
    ),
    (
        "The Adversary",
        "This fails on ownership. Nobody in the plan is accountable for the boring middle, and the middle is where every version of this has died before.",
    ),
    (
        "The Voice of Reason",
        "The facts support a small test, not a launch. Two weeks of real use will tell you more than another month of planning.",
    ),
    (
        "The Whistleblower",
        "The thing nobody is saying: this is a feature, not a product, and everyone in the room already knows it. Say it now while it is still cheap.",
    ),
    (
        "The Evangelist",
        "It matters because it lets one person do work that used to require a team. The blind spot is that the same person is the buyer, the user, and the support line.",
    ),
    (
        "The Fixer",
        "1. Name one owner. 2. Ship the smallest version this week. 3. Log every session and review the log in fourteen days.",
    ),
    (
        "You are the Producer",
        "CONTENDER 0 — YOUR IDEA: the seed as pitched. Customer: solo builders. Price: $12/mo. Wedge: one command, local-first. First ten: your own timeline. Dies on: whether anyone wants a fourth note-taking tool.\nCONTENDER 1 — THE CHEAP ONE: one button, $0 + tips. Wedge: no setup. First ten: a Reddit thread. Dies on: no support model.\nCONTENDER 2 — THE PREMIUM ONE: done-for-you at $2,500/mo. Wedge: white glove. First ten: warm intros. Dies on: founder time.\nCONTENDER 3 — THE NICHE WEDGE: only roofing contractors, $99/mo. Wedge: pre-filled quotes. First ten: one trade group. Dies on: a narrow market that will not pay.",
    ),
    (
        "You are the Critic",
        "YOUR IDEA: the weakest assumption is that the user wants another tool. Cheap One: free has no support loop. Premium One: the founder is the product. Niche Wedge: distribution depends on a group you do not belong to. All four are missing evidence that anyone pays twice.",
    ),
    (
        "You are the Foreman",
        "Winner: THE NICHE WEDGE. Deciding difference: it can name its first ten customers this week. Eliminated: YOUR IDEA — a feature looking for a buyer. Ranking: Niche Wedge, Premium, Cheap, Yours.",
    ),
    (
        "You are the Architect. Turn the winning contender",
        "Slice: one trade, one template, one quote. Files: `app.py`, `templates/roofing.md`, `tests/test_quote.py`. First story: a roofer pastes a job note and gets a quote in 30 seconds. Timebox: two sessions. Defer: accounts, sync, other trades.",
    ),
    (
        "You are the Coroner",
        "Your idea died of distribution, not quality. The smallest change that would have saved it: pick one trade and one repeated job, and sell the output before building the app. Risk for the winner: the niche is real but small; price the second template before the first invoice.",
    ),
    (
        "You are the Analyst",
        "The user is not short of tools; they are short of a decision. Evidence: none yet, only the founder's certainty. The assumption that kills this: people record a memo and never open the list.",
    ),
    (
        "You are the PM.",
        "Product: a memo-to-tasks CLI that prints a checklist in one command. Must-haves: record, transcribe locally, extract three actions. Non-goals: sync, accounts, a mobile app. Metric: one memo into tasks in under a minute. Slice: `memo <file>` prints tasks.",
    ),
    (
        "You are the Architect.",
        "Slice: `memo <file>` → local transcription → one model call → Markdown list on stdout. Interfaces: `transcribe(path) -> str`, `extract(text) -> list[str]`. Storage: none. Risky dependency: the local model's output discipline. Defer: editing, priorities, integrations.",
    ),
    (
        "You are the Builder.",
        "Files: `hotseat_core/memo.py`, `tests/test_memo.py`. Interface: `extract_tasks(text: str) -> list[str]`. First test: a three-sentence memo returns two tasks and drops the greeting. Timebox: one session. Done today: the CLI runs on a sample memo.",
    ),
    (
        "You are QA and the closer.",
        "Acceptance: a sample memo yields 1–5 tasks; no task is a greeting; output is valid Markdown. Kill criteria: transcription needs a cloud key, or tasks are invented. Cut: speaker diarization. GO — the slice is one afternoon and the risk is testable.",
    ),
)

_DEMO_FOOTER = "\n\n_(demo output — no model was called)_"


def demo_response(system: str | None, messages: list[Mapping[str, str]]) -> str:
    """Return a deterministic, clearly labeled stand-in reply."""

    haystack = " ".join([system or ""] + [str(m.get("content", "")) for m in messages])
    for name, line in DEMO_LINES:
        if name in haystack:
            return line + _DEMO_FOOTER
    return "This is the demo provider. Set a real provider and key to hear the panel." + _DEMO_FOOTER


def _get_secret(key: str, secret_loader: Callable[[str, str], str] | None = None) -> str:
    """Call the repository's vault_loader lazily; environment overrides remain first."""

    if os.environ.get(key):
        return os.environ[key]
    try:
        if secret_loader is None:
            # Delayed import means missing vaults/keys never break module import.
            from vault_loader import get_secret

            secret_loader = get_secret
        return str(secret_loader(key, "") or "")
    except (ImportError, OSError, ValueError):
        return ""


def _provider_url(spec: ProviderSpec) -> str:
    override = os.environ.get(f"{spec.name.upper()}_BASE_URL", "").strip()
    return (override or spec.base_url).rstrip("/")


def probe_9router(timeout: float = 0.25, *, host: str = "127.0.0.1", port: int = 20128) -> bool:
    """Fast TCP health check; a reachable listener is enough to select it."""

    try:
        with socket.create_connection((host, port), timeout=max(0.01, timeout)):
            return True
    except OSError:
        return False


def _configured_cloud_provider(
    secret_loader: Callable[[str, str], str] | None = None,
) -> tuple[str, str] | None:
    for name in _CLOUD_ORDER:
        spec = PROVIDERS[name]
        for key_name in spec.credential_names:
            key = _get_secret(key_name, secret_loader)
            if key:
                return name, key
    return None


def resolve_provider(
    provider: str = "auto",
    *,
    secret_loader: Callable[[str, str], str] | None = None,
    health_probe: Callable[[], bool] = probe_9router,
) -> "ProviderClient":
    """Resolve an explicit provider, or probe local 9router first in auto mode.

    In auto mode, when 9router is not listening, configured cloud credentials are
    checked in a deterministic order. If none are available, OpenRouter is selected
    and its missing-key error is reported on the first request. No credential is
    loaded for an unselected explicit provider.
    """

    requested = (provider or "auto").strip().lower()
    if requested == "auto":
        if health_probe():
            return ProviderClient("9router", secret_loader=secret_loader)
        cloud = _configured_cloud_provider(secret_loader)
        if cloud:
            name, key = cloud
            return ProviderClient(name, api_key=key, secret_loader=secret_loader)
        return ProviderClient("openrouter", secret_loader=secret_loader)

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
    secret_loader: Callable[[str, str], str] | None = field(default=None, repr=False)
    spec: ProviderSpec = field(init=False, repr=False)
    base_url: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise ProviderError(f"Unknown provider '{self.provider}'.")
        self.spec = PROVIDERS[self.provider]
        self.base_url = _provider_url(self.spec)
        if self.api_key is None and self.spec.needs_key:
            self.api_key = self._load_selected_key()

    def _load_selected_key(self) -> str:
        for key_name in self.spec.credential_names:
            key = _get_secret(key_name, self.secret_loader)
            if key:
                return key
        raise ProviderError(
            f"Provider '{self.provider}' requires a credential. Set "
            f"{' or '.join(self.spec.credential_names)} in the environment or ~/.concierge/vault.json."
        )

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

        selected_model = (
            model
            or os.environ.get(f"{self.provider.upper()}_MODEL")
            or self.spec.default_model
        )
        options = dict(sampling or {})

        if self.spec.protocol == "demo":
            text = demo_response(system, messages)
            if on_chunk:
                on_chunk(text)
            return text

        if on_chunk is None or self.spec.protocol == "anthropic":
            text = self._complete_once(messages, selected_model, system, options)
            if on_chunk:
                on_chunk(text)
            return text
        return self._complete_stream(messages, selected_model, system, options, on_chunk)

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
            headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
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
                f"Provider '{self.provider}' returned an unexpected response format."
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
            suffix = f": {detail}" if detail else ""
            raise ProviderError(f"Provider '{self.provider}' returned HTTP {exc.code}{suffix}.") from None
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", None) or exc
            raise ProviderError(f"Could not reach provider '{self.provider}': {reason}.") from None
        except ValueError as exc:
            raise ProviderError(f"Provider '{self.provider}' returned invalid stream data: {exc}.") from None
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
                        raise ProviderError(f"Provider '{self.provider}' returned invalid JSON data.")
                    return parsed
            except HTTPError as exc:
                # Retry rate limits and transient server errors, but not client errors.
                if attempt + 1 < attempts and (exc.code == 429 or exc.code >= 500):
                    time.sleep(min(0.2 * (2**attempt), 1.0))
                    continue
                detail = self._http_error_detail(exc)
                suffix = f": {detail}" if detail else ""
                raise ProviderError(f"Provider '{self.provider}' returned HTTP {exc.code}{suffix}.") from None
            except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(0.2 * (2**attempt), 1.0))
                    continue
                reason = getattr(exc, "reason", None) or exc
                raise ProviderError(f"Could not reach provider '{self.provider}': {reason}.") from None
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProviderError(f"Provider '{self.provider}' returned invalid JSON: {exc}.") from None
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
