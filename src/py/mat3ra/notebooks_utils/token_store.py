"""Persist OIDC tokens across notebook kernels."""

import time
from typing import Optional

from .primitive.environment import is_pyodide_environment

if is_pyodide_environment():
    from .pyodide.api import token_store as _storage
else:
    from .core.api import token_store as _storage  # type: ignore[no-redef]

_EXPIRY_BUFFER = 60  # seconds before actual expiry to consider token stale


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
