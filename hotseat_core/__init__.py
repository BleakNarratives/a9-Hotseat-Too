"""Modular Hotseat runtime.

This package is the supported engine. The desktop console and ``/m`` companion
assets are bundled under ``hotseat_core/web`` and resolved from package
resources, so an installed wheel serves the same UI as a source checkout. It has
no third-party dependencies for local use: provider transport is ``urllib``,
storage is ``sqlite3``, and the bridge is ``http.server``.

Quick start::

    python -m hotseat_core --provider demo "ship the small version"
    python -m hotseat_core --mode v3 --variant tribunal "hire or contract?"
    python -m hotseat_core --mode bmad "brief this build in one pass"
    python -m hotseat_core --mode arena "your idea vs three rivals"
    python -m hotseat_core --serve
"""

from .config import HotseatConfig, load_config
from .personas import MODES, Persona, PersonaSet, get_persona_set, list_modes
from .providers import ProviderClient, ProviderError, available_providers, resolve_provider
from .runtime import HotseatRuntime, SessionResult
from .storage import SessionStore, StorageError
from .tuning import STYLE_PROFILES, clean_response, compose_styles

__all__ = [
    "HotseatConfig",
    "HotseatRuntime",
    "MODES",
    "Persona",
    "PersonaSet",
    "ProviderClient",
    "ProviderError",
    "STYLE_PROFILES",
    "SessionResult",
    "SessionStore",
    "StorageError",
    "available_providers",
    "clean_response",
    "compose_styles",
    "get_persona_set",
    "list_modes",
    "load_config",
    "resolve_provider",
]

__version__ = "0.5.0"
