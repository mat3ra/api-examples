"""Persist OIDC tokens across notebook kernels — thin routing adapter."""

from .core.api.token_store import load_token, save_token  # noqa: F401 — re-export
from .primitive.environment import is_pyodide_environment

if is_pyodide_environment():
    from .core.api import token_store as _core_ts
    from .pyodide.api import token_store as _pyodide_storage

    _core_ts._storage = _pyodide_storage
