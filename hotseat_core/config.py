"""Configuration loading for the additive Hotseat core package.

Configuration is deliberately side-effect free: importing this module does not
read credentials, touch databases, or create directories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class HotseatConfig:
    """Normalized application configuration sourced from an optional manifest."""

    root: Path
    manifest_path: Path | None = None
    provider: str = "auto"
    model: str | None = None
    styles: tuple[str, ...] = ()
    personas: Mapping[str, Any] = field(default_factory=dict)
    provider_options: Mapping[str, Any] = field(default_factory=dict)
    raw_manifest: Mapping[str, Any] = field(default_factory=dict)


def load_config(
    manifest_path: str | Path | None = None,
    *,
    root: str | Path | None = None,
) -> HotseatConfig:
    """Load supported settings from JSON without requiring a manifest.

    The conventional manifest is ``manifest.json`` at ``root`` (or the current
    working directory). Recognized optional keys are ``provider``, ``model``,
    ``styles`` / ``style``, ``personas``, and ``provider_options``. Existing
    legacy manifest layouts are accepted; unrecognized keys are preserved in
    ``raw_manifest`` and ignored by the core.
    """

    base = Path(root) if root is not None else Path.cwd()
    selected = Path(manifest_path) if manifest_path is not None else base / "manifest.json"
    if not selected.is_absolute():
        selected = base / selected if manifest_path is not None else selected

    data: dict[str, Any] = {}
    if selected.is_file():
        try:
            parsed = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot load manifest {selected}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Manifest must contain a JSON object: {selected}")
        data = parsed

    # Accept both a simple core section and top-level keys, while avoiding
    # assumptions about the older metadata-only manifest schema.
    core = data.get("hotseat_core", {})
    if not isinstance(core, dict):
        core = {}

    styles_value = core.get("styles", data.get("styles", data.get("style", ())))
    if isinstance(styles_value, str):
        styles = tuple(s.strip() for s in styles_value.split(",") if s.strip())
    elif isinstance(styles_value, (list, tuple)):
        styles = tuple(str(s).strip() for s in styles_value if str(s).strip())
    else:
        styles = ()

    personas = core.get("personas", data.get("personas", {}))
    provider_options = core.get("provider_options", data.get("provider_options", {}))
    if not isinstance(personas, dict):
        personas = {}
    if not isinstance(provider_options, dict):
        provider_options = {}

    return HotseatConfig(
        root=base.resolve(),
        manifest_path=selected if selected.is_file() else None,
        provider=str(core.get("provider", data.get("provider", "auto"))),
        model=core.get("model", data.get("model")),
        styles=styles,
        personas=personas,
        provider_options=provider_options,
        raw_manifest=data,
    )
