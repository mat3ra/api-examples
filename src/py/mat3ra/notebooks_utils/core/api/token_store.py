"""File-based OIDC token cache (~/.mat3ra/oidc_token_cache.json, 0o600)."""

import json
import os

_PATH = os.path.join(os.path.expanduser("~"), ".mat3ra", "oidc_token_cache.json")


async def read() -> dict:
    try:
        with open(_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


async def write(cache: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), mode=0o700, exist_ok=True)
    with open(_PATH, "w") as f:
        json.dump(cache, f)
    os.chmod(_PATH, 0o600)
