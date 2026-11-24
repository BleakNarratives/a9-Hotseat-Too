"""Compatibility shim: secrets now live inside the package.

Prefer ``from hotseat_core.vault_loader import get_secret``.
"""

from hotseat_core.vault_loader import *  # noqa: F401,F403
