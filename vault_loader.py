import json
import os
from pathlib import Path

VAULT_PATH = Path.home() / ".concierge" / "vault.json"

def get_secret(key_name: str, default: str = "") -> str:
    if os.environ.get(key_name):
        return os.environ[key_name]
    if VAULT_PATH.exists():
        try:
            data = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if key_name in data and data[key_name]:
                    return str(data[key_name])
                for section in ("keys", "secrets", "providers", "openrouter"):
                    sub = data.get(section)
                    if isinstance(sub, dict) and sub.get(key_name):
                        return str(sub[key_name])
        except Exception:
            pass
    return default
