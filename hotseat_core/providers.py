"""Small unified chat-completion client for local and hosted providers.

Provider credentials are resolved only when selection requires them. The
module uses the standard library transport so local-first installs do not need
an extra HTTP package merely to import Hotseat.
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
        "openrouter", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY", "OPENROUTER_KEY"), "openai/gpt-4o-mini", needs_key=True
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
}

_CLOUD_ORDER = ("openrouter", "anthropic", "mistral", "cerebras", "groq")


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
    env_names = {
        "9router": "NINEROUTER_BASE_URL",
        "ai_gateway": "AI_GATEWAY_BASE_URL",
        "ollama": "OLLAMA_BASE_URL",
    }
    override = os.environ.get(env_names.get(spec.name, ""), "").strip()
    if override:
        return override.rstrip("/")
    if spec.name == "9router":
        return os.environ.get("NINEROUTER_BASE_URL", spec.base_url).rstrip("/")
    return spec.base_url.rstrip("/")


def probe_9router(timeout: float = 0.25, *, host: str = "127.0.0.1", port: int = 20128) -> bool:
    """Fast TCP health check; a reachable HTTP listener is enough to select it.

    ``socket.create_connection`` has a short bounded timeout and closes the
    socket immediately, so this does not wait on a model generation or API key.
    """

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
    """Resolve explicit provider selection or auto-probe local 9router first.

    In auto mode, when 9router is not listening, configured cloud credentials
    are checked in a deterministic order. If none are available, OpenRouter is
    selected as the default and its missing-key error is reported on request.
    No credential is loaded for unselected explicit providers.
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
    """Resolved provider plus retrying JSON request implementation."""

    provider: str
    api_key: str | None = None
    timeout: float = 30.0
    retries: int = 1
    secret_loader: Callable[[str, str], str] | None = field(default=None, repr=False)

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

    def complete(
        self,
        *,
        messages: list[Mapping[str, str]],
        model: str | None = None,
        system: str | None = None,
        sampling: Mapping[str, Any] | None = None,
    ) -> str:
        """Return assistant text from a messages-style chat request."""

        selected_model = model or os.environ.get(f"{self.provider.upper()}_MODEL") or self.spec.default_model
        options = dict(sampling or {})
        if self.spec.protocol == "anthropic":
            body = self._anthropic_body(messages, selected_model, system, options)
            path = "/messages"
            headers = {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}
        elif self.spec.protocol == "ollama":
            body = self._ollama_body(messages, selected_model, system, options)
            path = "/api/chat"
            headers = {}
        else:
            body = self._openai_body(messages, selected_model, system, options)
            path = "/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        payload = json.dumps(body).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
            method="POST",
        )
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
            raise ProviderError(f"Provider '{self.provider}' returned an unexpected response format.") from exc

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
                detail = ""
                try:
                    error_data = json.loads(exc.read().decode("utf-8"))
                    detail = error_data.get("error", {}).get("message", "") if isinstance(error_data, dict) else ""
                except (ValueError, OSError):
                    pass
                suffix = f": {detail[:300]}" if detail else ""
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

    @staticmethod
    def _openai_body(
        messages: list[Mapping[str, str]], model: str, system: str | None, options: Mapping[str, Any]
    ) -> dict[str, Any]:
        normalized = []
        if system:
            normalized.append({"role": "system", "content": system})
        normalized.extend({"role": str(m.get("role", "user")), "content": str(m.get("content", ""))} for m in messages)
        body: dict[str, Any] = {"model": model, "messages": normalized}
        allowed = {"temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "stop"}
        body.update({key: value for key, value in options.items() if key in allowed and value is not None})
        return body

    @staticmethod
    def _anthropic_body(
        messages: list[Mapping[str, str]], model: str, system: str | None, options: Mapping[str, Any]
    ) -> dict[str, Any]:
        normalized = [
            {"role": "assistant" if m.get("role") == "assistant" else "user", "content": str(m.get("content", ""))}
            for m in messages if m.get("role") != "system"
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
        messages: list[Mapping[str, str]], model: str, system: str | None, options: Mapping[str, Any]
    ) -> dict[str, Any]:
        normalized = []
        if system:
            normalized.append({"role": "system", "content": system})
        normalized.extend({"role": str(m.get("role", "user")), "content": str(m.get("content", ""))} for m in messages)
        ollama_options = {
            key: options[key]
            for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "num_predict")
            if key in options
        }
        if "max_tokens" in options:
            ollama_options["num_predict"] = options["max_tokens"]
        return {"model": model, "messages": normalized, "stream": False, "options": ollama_options}


def available_providers() -> list[dict[str, Any]]:
    """Return provider metadata without probing services or loading credentials."""

    return [
        {"name": name, "local": name in {"9router", "ai_gateway", "ollama"}, "requires_key": spec.needs_key}
        for name, spec in PROVIDERS.items()
    ]
