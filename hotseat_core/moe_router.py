"""Cloud-Only Mixture-of-Experts (MoE) & Multi-Provider Randomizer backed by ~/.concierge/vault.json."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any

# Pure cloud-API pools (zero local Ollama/Llama weight bloat)
ROLE_POOLS: dict[str, list[tuple[str, str]]] = {
    "critic": [
        ("xai", "grok-3-mini"),
        ("openrouter", "openrouter/free"),
        ("openrouter", "nvidia/nemotron-3-ultra:free"),
        ("groq", "openai/gpt-oss-120b"),
        ("gemini", "gemini-3.5-flash-lite"),
    ],
    "adversary": [
        ("xai", "grok-3-mini"),
        ("openrouter", "nvidia/nemotron-3-ultra:free"),
        ("openrouter", "deepseek/deepseek-r1:free"),
        ("groq", "openai/gpt-oss-120b"),
        ("gemini", "gemini-3.5-flash-lite"),
    ],
    "producer": [
        ("openrouter", "openrouter/free"),
        ("groq", "openai/gpt-oss-120b"),
        ("cerebras", "gpt-oss-120b"),
        ("gemini", "gemini-3.5-flash-lite"),
    ],
    "foreman": [
        ("deepseek", "deepseek-chat"),
        ("openrouter", "deepseek/deepseek-r1:free"),
        ("xai", "grok-3-mini"),
        ("gemini", "gemini-3.5-flash-lite"),
    ],
    "architect": [
        ("openrouter", "google/gemma-4-31b-it:free"),
        ("deepseek", "deepseek-chat"),
        ("cerebras", "qwen-3-32b"),
        ("gemini", "gemini-3.8-flash"),
    ],
    "coroner": [
        ("xai", "grok-3-mini"),
        ("openrouter", "nvidia/nemotron-3-ultra:free"),
        ("groq", "openai/gpt-oss-120b"),
        ("gemini", "gemini-3.5-flash-lite"),
    ],
}

ENV_MAP = {
    "xai": ("XAI_API_KEY", "GROK_API_KEY", "xai", "grok"),
    "openrouter": ("OPENROUTER_API_KEY", "openrouter"),
    "groq": ("GROQ_API_KEY", "groq"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek"),
    "cerebras": ("CEREBRAS_API_KEY", "cerebras"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini"),
}


def hydrate_vault_keys() -> set[str]:
    """Load API keys from ~/.concierge/vault.json into os.environ without echoing secrets."""
    available: set[str] = set()
    vault_data: dict[str, Any] = {}
    for path in (
        Path.home() / ".concierge" / "vault.json",
        Path.home() / ".concierge" / "vault.v3.json",
    ):
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    vault_data.update(raw)
                    if isinstance(raw.get("keys"), dict):
                        vault_data.update(raw["keys"])
            except Exception:
                pass

    for provider, aliases in ENV_MAP.items():
        primary_env = aliases[0]
        if os.environ.get(primary_env):
            available.add(provider)
            continue
        for alias in aliases:
            val = os.environ.get(alias) or vault_data.get(alias)
            if isinstance(val, str) and val.strip():
                os.environ[primary_env] = val.strip()
                available.add(provider)
                break
    return available


def pick_seat_route(role_key: str, *, randomize: bool = False) -> tuple[str, str]:
    """Return (provider, model) for a seat across active cloud vault providers."""
    active = hydrate_vault_keys()
    pool = ROLE_POOLS.get(role_key) or [
        item for sublist in ROLE_POOLS.values() for item in sublist
    ]
    candidates = [(prov, mod) for prov, mod in pool if prov in active]
    if not candidates:
        # Do not invent a provider with no credential; let the normal auto
        # selector report readiness and use its own fallback chain.
        return ("", "")
    return random.choice(candidates) if randomize else candidates[0]
