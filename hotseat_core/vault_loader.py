"""Runtime secret resolution for Hotseat providers.

Precedence: environment (exact key, then aliases) → repository ``.env`` → the
Concierge vault at ``~/.concierge/vault.json``.

The vault is searched recursively, so nested layouts work without configuration::

    {"version": 3, "keys": {"OPENROUTER_KEY": "..."}, "mistral": "..."}
    {"providers": {"anthropic": {"api_key": "..."}}}
    {"secrets": [{"name": "GROQ_API_KEY", "value": "..."}]}

Key matching is case-insensitive and alias-aware: asking for
``OPENROUTER_API_KEY`` also finds ``OPENROUTER_KEY``, ``openrouter``, or an
``openrouter`` section containing ``api_key``/``key``/``token``/``value``.

Nothing here prints, logs, or mutates the environment.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

DEFAULT_VAULT_PATH = Path.home() / ".concierge" / "vault.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

_SECRET_SUFFIXES = ("API_KEY", "KEY", "TOKEN", "SECRET")
_LEAF_NAMES = ("api_key", "apikey", "key", "token", "secret", "value")


def _normalize(name: Any) -> str:
    """Normalize a key or section name for case-insensitive comparison."""

    return re.sub(r"[^A-Z0-9]+", "_", str(name).upper()).strip("_")


def _aliases(key_name: str) -> set[str]:
    normalized = _normalize(key_name)
    base = normalized
    for suffix in _SECRET_SUFFIXES:
        if base.endswith("_" + suffix):
            base = base[: -(len(suffix) + 1)]
            break
    aliases = {normalized, base}
    aliases.update(base + "_" + suffix for suffix in _SECRET_SUFFIXES)
    return {alias for alias in aliases if alias}


def _clean(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _leaf_secret(node: Any) -> str | None:
    """Extract a scalar secret from a provider-ish dict/list."""

    if isinstance(node, str):
        return _clean(node)
    if isinstance(node, Mapping):
        normalized = {_normalize(key): value for key, value in node.items()}
        for leaf in _LEAF_NAMES:
            found = _clean(normalized.get(_normalize(leaf)))
            if found:
                return found
        for value in node.values():
            # Only descend into containers here. Returning the first scalar in a
            # provider section could mistake a base URL or model name for a key.
            if isinstance(value, (Mapping, list)):
                found = _leaf_secret(value)
                if found:
                    return found
    elif isinstance(node, list):
        for item in node:
            found = _leaf_secret(item)
            if found:
                return found
    return None


def _find_secret(node: Any, aliases: set[str]) -> str | None:
    """Depth-first search for an alias, descending through dicts and lists."""

    if isinstance(node, Mapping):
        for key, value in node.items():
            normalized = _normalize(key)
            if normalized in aliases:
                found = _leaf_secret(value)
                if found:
                    return found
            if isinstance(value, (Mapping, list)):
                found = _find_secret(value, aliases)
                if found:
                    return found
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, Mapping):
                # Named-secret lists: [{"name": "GROQ_API_KEY", "value": "..."}]
                for id_key in ("name", "provider", "service", "id", "key_name"):
                    identifier = item.get(id_key)
                    if isinstance(identifier, str) and _normalize(identifier) in aliases:
                        found = _leaf_secret(item)
                        if found:
                            return found
            found = _find_secret(item, aliases)
            if found:
                return found
    return None


def _read_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}

    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            values[_normalize(key)] = value
    return values


def _load_vault(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, Mapping) else {}


def get_secret(
    key_name: str,
    default: str = "",
    *,
    vault_path: str | Path | None = None,
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve one secret without requiring shell exports.

    The optional arguments exist so tests (and embedding applications) can point
    at isolated files without touching the user's home directory.
    """

    if not key_name:
        return default

    environment = os.environ if environ is None else environ
    aliases = _aliases(key_name)

    if environment.get(key_name):
        return environment[key_name]
    for alias in sorted(aliases):
        value = environment.get(alias)
        if value:
            return value

    env_values = _read_env_file(
        Path(env_file).expanduser() if env_file is not None else DEFAULT_ENV_FILE
    )
    for alias in sorted(aliases):
        value = env_values.get(alias)
        if value:
            return value

    selected_vault = Path(vault_path).expanduser() if vault_path is not None else DEFAULT_VAULT_PATH
    value = _find_secret(_load_vault(selected_vault), aliases)
    return value or default
