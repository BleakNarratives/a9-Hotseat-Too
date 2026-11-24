"""Modular Hotseat runtime primitives.

The legacy implementations remain untouched; new orchestration code can build on
this package without importing their optional UI or model dependencies.
"""

from .config import HotseatConfig, load_config
from .providers import ProviderClient, ProviderError, resolve_provider
from .tuning import clean_response, compose_styles

__all__ = [
    "HotseatConfig",
    "ProviderClient",
    "ProviderError",
    "clean_response",
    "compose_styles",
    "load_config",
    "resolve_provider",
]

__version__ = "0.1.0"
