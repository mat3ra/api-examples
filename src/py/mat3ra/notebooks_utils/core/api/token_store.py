"""OIDC token cache — business logic + file-based storage (default)."""

import json
import os
import sys
import time
from typing import Optional

_EXPIRY_BUFFER = 60  # seconds before actual expiry to consider token stale
_FILE_PATH = os.path.join(os.path.expanduser("~"), ".mat3ra", "oidc_token_cache.json")

# Storage backend: defaults to this module (file-based).
# Overridden by top-level token_store.py for Pyodide (IndexedDB).
_storage = sys.modules[__name__]


async def read() -> dict:
    try:
        with open(_FILE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


async def write(cache: dict) -> None:
    os.makedirs(os.path.dirname(_FILE_PATH), mode=0o700, exist_ok=True)
    with open(_FILE_PATH, "w") as f:
        json.dump(cache, f)
    os.chmod(_FILE_PATH, 0o600)


async def save_token(oidc_url: str, token_data: dict) -> None:
    token_cache_entry = dict(token_data)
    token_cache_entry["expires_at"] = time.time() + token_cache_entry.get("expires_in", 3600)

    token_cache = await _storage.read()
    token_cache[oidc_url] = token_cache_entry
    await _storage.write(token_cache)


async def load_token(oidc_url: str) -> Optional[dict]:
    token_cache_entry = (await _storage.read()).get(oidc_url)

    if not token_cache_entry:
        return None

    expires_at = token_cache_entry.get("expires_at", 0)
    if expires_at <= time.time() + _EXPIRY_BUFFER:
        return None

    return token_cache_entry
