"""Persist OIDC tokens across notebook kernels (localStorage or file)."""

import json
import os
import time

from .primitive.environment import is_pyodide_environment

_USE_BROWSER = is_pyodide_environment()
if _USE_BROWSER:
    import js  # type: ignore

_FILE_PATH = os.path.join(os.path.expanduser("~"), ".mat3ra", "oidc_token_cache.json")
_LOCAL_STORAGE_KEY = "mat3ra_oidc_token_cache"
_EXPIRY_BUFFER = 60  # seconds before actual expiry to consider token stale


def save_token(oidc_url: str, token_data: dict) -> None:
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    cache = _read_cache()
    cache[oidc_url] = token_data
    _write_cache(cache)


def load_token(oidc_url: str):
    data = _read_cache().get(oidc_url)
    if data and data.get("expires_at", 0) > time.time() + _EXPIRY_BUFFER:
        return data
    return None


def _read_cache() -> dict:
    if _USE_BROWSER:
        return json.loads(js.localStorage.getItem(_LOCAL_STORAGE_KEY) or "{}")
    try:
        with open(_FILE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(cache: dict) -> None:
    if _USE_BROWSER:
        js.localStorage.setItem(_LOCAL_STORAGE_KEY, json.dumps(cache))
    else:
        os.makedirs(os.path.dirname(_FILE_PATH), mode=0o700, exist_ok=True)
        with open(_FILE_PATH, "w") as f:
            json.dump(cache, f)
        os.chmod(_FILE_PATH, 0o600)
