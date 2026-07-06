"""Persist OIDC tokens across notebook kernels.

Switches storage between file (Python) and IndexedDB (Pyodide).
"""

import time
from typing import Optional

from .primitive.environment import is_pyodide_environment

if is_pyodide_environment():
    from .pyodide.api.token_store import read as _read
    from .pyodide.api.token_store import write as _write
else:
    from .core.api.token_store import read as _read
    from .core.api.token_store import write as _write

_EXPIRY_BUFFER = 60 * 5  # to avoid using soon-to-expire tokens


async def save_token(oidc_url: str, token_data: dict) -> None:
    entry = dict(token_data)
    entry["expires_at"] = time.time() + entry.get("expires_in", 3600)
    cache = await _read()
    cache[oidc_url] = entry
    await _write(cache)


async def load_token(oidc_url: str) -> Optional[dict]:
    entry = (await _read()).get(oidc_url)
    if not entry or entry.get("expires_at", 0) <= time.time() + _EXPIRY_BUFFER:
        return None
    return entry
