"""Persist OIDC tokens across notebook kernels.

Switches storage between file (Python) and IndexedDB (Pyodide).
"""

from typing import Optional

from mat3ra.api_client.tools.auth.token import add_token_to_cache, get_token_from_cache

from .primitive.environment import is_pyodide_environment

if is_pyodide_environment():
    from .pyodide.api.token_store import read as _read
    from .pyodide.api.token_store import write as _write
else:
    from .core.api.token_store import read as _read
    from .core.api.token_store import write as _write


async def save_token(oidc_url: str, token_data: dict) -> None:
    cache = await _read()
    add_token_to_cache(cache, oidc_url, token_data)
    await _write(cache)


async def load_token(oidc_url: str) -> Optional[dict]:
    return get_token_from_cache(await _read(), oidc_url)


async def delete_token(oidc_url: str) -> None:
    cache = await _read()
    cache.pop(oidc_url, None)
    await _write(cache)
