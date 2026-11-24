"""Configuration loading for the Hotseat core runtime.

Configuration is deliberately side-effect free: importing this module does not
read credentials, touch databases, or create directories.

Precedence, highest first: explicit arguments (via :func:`dataclasses.replace`),
environment variables, ``manifest.json`` (optionally with a ``hotseat_core``
section), built-in defaults. ``manifest.json`` is optional; a checkout with only
the tracked metadata manifest loads with defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

#: Legacy default. The classic Termux install keeps memory.db and sessions.log
#: here, so pointing the core at it makes migration automatic.
DEFAULT_DATA_DIR = Path.home() / "hotseat"


@dataclass(frozen=True)
class HotseatConfig:
    """Normalized application configuration."""

    root: Path
    manifest_path: Path | None = None
    provider: str = "auto"
    model: str | None = None
    styles: tuple[str, ...] = ()
    personas: Mapping[str, Any] = field(default_factory=dict)
    role_models: Mapping[str, Any] = field(default_factory=dict)
    provider_options: Mapping[str, Any] = field(default_factory=dict)
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    db_path: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "memory.db")
    session_log: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "sessions.log")
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8765
    raw_manifest: Mapping[str, Any] = field(default_factory=dict)

    def persona_overrides(self, mode: str, variant: str | None = None) -> Mapping[str, Any]:
        """Return per-persona overrides for a mode, or an empty mapping.

        Accepted manifest layouts::

            {"hotseat_core": {"personas": {"classic": {"audrey": {"model": "..."}}}}}
            {"hotseat_core": {"personas": {"v3:tribunal": {"fixer": {"model": "..."}}}}}
            {"hotseat_core": {"personas": {"audrey": {"model": "..."}}}}   # all modes
        """

        if not isinstance(self.personas, Mapping):
            return {}
        candidates = []
        if variant:
            candidates.extend((f"{mode}:{variant}", f"{mode}.{variant}"))
        candidates.extend((mode, "*", "default"))
        for key in candidates:
            section = self.personas.get(key)
            if isinstance(section, Mapping):
                return section
        # Flat layout: every value is a persona mapping and no key looks like a mode.
        known_modes = {"classic", "v2", "v3", "*", "default"}
        if self.personas and all(isinstance(value, Mapping) for value in self.personas.values()):
            if not any(
                key in known_modes or ":" in key or "." in key for key in self.personas
            ):
                return self.personas
        return {}

    def role_models_for(
        self, mode: str, variant: str | None = None
    ) -> Mapping[str, str]:
        """Resolve manifest role-model defaults for a mode/variant.

        Accepted layouts::

            {"role_models": {"producer": "fast-model"}}
            {"role_models": {"arena": {"producer": "fast-model"}}}
            {"role_models": {"arena": {"season": {"producer": "fast-model"}}}}
        """

        data = self.role_models
        if not isinstance(data, Mapping) or not data:
            return {}
        section = data.get(mode)
        if isinstance(section, Mapping):
            if variant and isinstance(section.get(variant), Mapping):
                return {
                    str(key): str(value)
                    for key, value in section[variant].items()
                    if value not in (None, "")
                }
            return {
                str(key): str(value)
                for key, value in section.items()
                if isinstance(value, str) and value
            }
        for key in (f"{mode}:{variant}" if variant else None, "*", "default"):
            if not key:
                continue
            candidate = data.get(key)
            if isinstance(candidate, Mapping):
                return {
                    str(role): str(model)
                    for role, model in candidate.items()
                    if isinstance(model, str) and model
                }
        if all(isinstance(value, str) for value in data.values()):
            return {str(key): str(value) for key, value in data.items() if value}
        return {}


def _manifest_core(data: Mapping[str, Any]) -> Mapping[str, Any]:
    core = data.get("hotseat_core", {})
    return core if isinstance(core, Mapping) else {}


def _styles(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _resolve(base: Path, value: Any, fallback: Path) -> Path:
    if value in (None, ""):
        return fallback
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (base / path)


def load_config(
    manifest_path: str | Path | None = None,
    *,
    root: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> HotseatConfig:
    """Load supported settings without requiring a manifest.

    The conventional manifest is ``manifest.json`` at ``root`` (or the current
    working directory). Recognized optional keys live either at the top level or
    inside a ``hotseat_core`` object: ``provider``, ``model``, ``styles`` /
    ``style``, ``personas``, ``provider_options``, ``data_dir``, ``db_path``,
    ``session_log``, and ``bridge`` (``host`` / ``port``). Legacy manifest
    layouts are accepted; unrecognized keys are preserved in ``raw_manifest``.
    """

    environ = os.environ if env is None else env
    base = Path(root).expanduser() if root is not None else Path.cwd()
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    else:
        base = base.resolve()

    if manifest_path is None:
        candidates = [base / "manifest.json"]
    else:
        candidates = [Path(manifest_path).expanduser()]
        candidates = [p if p.is_absolute() else base / p for p in candidates]

    selected = next((path for path in candidates if path.is_file()), None)
    data: dict[str, Any] = {}
    if selected is not None:
        try:
            parsed = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot load manifest {selected}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Manifest must contain a JSON object: {selected}")
        data = parsed

    core = _manifest_core(data)
    bridge = _mapping(core.get("bridge", data.get("bridge", {})))

    data_dir = _resolve(
        base,
        environ.get("HOTSEAT_DATA_DIR")
        or core.get("data_dir", data.get("data_dir")),
        DEFAULT_DATA_DIR,
    )
    db_path = _resolve(
        base,
        environ.get("HOTSEAT_DB")
        or core.get("db_path", data.get("db_path")),
        data_dir / "memory.db",
    )
    session_log = _resolve(
        base,
        environ.get("HOTSEAT_SESSION_LOG")
        or core.get("session_log", data.get("session_log")),
        data_dir / "sessions.log",
    )

    provider = (
        environ.get("HOTSEAT_PROVIDER")
        or core.get("provider", data.get("provider"))
        or "auto"
    )
    model = environ.get("HOTSEAT_MODEL") or core.get("model", data.get("model"))
    styles = _styles(
        environ.get("HOTSEAT_STYLES")
        if environ.get("HOTSEAT_STYLES") is not None
        else core.get("styles", data.get("styles", data.get("style")))
    )

    host = (
        environ.get("HOTSEAT_BRIDGE_HOST")
        or bridge.get("host", core.get("bridge_host"))
        or "127.0.0.1"
    )
    port_value: Any = (
        environ.get("HOTSEAT_BRIDGE_PORT")
        or bridge.get("port", core.get("bridge_port"))
        or 8765
    )
    try:
        port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid bridge port: {port_value!r}") from exc
    if not 0 <= port <= 65535:
        raise ValueError(f"Bridge port out of range: {port}")

    return HotseatConfig(
        root=base,
        manifest_path=selected,
        provider=str(provider),
        model=str(model) if model else None,
        styles=styles,
        personas=_mapping(core.get("personas", data.get("personas"))),
        role_models=_mapping(core.get("role_models", data.get("role_models"))),
        provider_options=_mapping(
            core.get("provider_options", data.get("provider_options"))
        ),
        data_dir=data_dir,
        db_path=db_path,
        session_log=session_log,
        bridge_host=str(host),
        bridge_port=port,
        raw_manifest=data,
    )
