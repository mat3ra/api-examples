"""Notebook authentication.

Two paths depending on environment:

1. JupyterLite embedded in WebApp — the host app injects a token via
   postMessage and authenticate_jupyterlite() stores it in the environment.

2. Standalone / IDE / local dev — OIDC device-code flow. Tokens are cached
   (file on disk or IndexedDB in Pyodide) so the user only logs in once
   per expiry window.
"""

import inspect
import os

from mat3ra.api_client import ACCESS_TOKEN_ENV_VAR

from .core.api.auth import authenticate_oidc, get_oidc_base_url, store_token_data_in_environment
from .io import get_data
from .ipython.ui import show_device_flow_popup
from .primitive.environment import is_pyodide_environment
from .pyodide.api.auth import authenticate_jupyterlite
from .token_store import load_token, save_token

REFRESH_TOKEN_ENV_VAR = "OIDC_REFRESH_TOKEN"


async def _authenticate_oidc_with_cache(force=False):
    oidc_url = get_oidc_base_url()
    cached = None if force else await load_token(oidc_url)

    if cached:
        store_token_data_in_environment(cached)
        return

    token_data = await authenticate_oidc(show_popup=show_device_flow_popup)
    await save_token(oidc_url, token_data)


async def authenticate(force=False, globals_dict=None):
    """
    Authenticate the current notebook session with the Mat3ra platform.
    Follow the link to a new browser window to complete the authentication process.
    The token is cached in the environment for future use.

    Args:
        force: Re-authenticate even if a valid cached token exists.
        globals_dict: Caller's global namespace. Auto-detected if not provided.
    """
    if globals_dict is None:
        frame = inspect.currentframe()
        try:
            globals_dict = frame.f_back.f_globals  # type: ignore
        finally:
            del frame

    if is_pyodide_environment():
        get_data("data_from_host", globals_dict)

    data_from_host = globals_dict.get("data_from_host")

    if data_from_host:
        await authenticate_jupyterlite(data_from_host)
    elif ACCESS_TOKEN_ENV_VAR not in os.environ or force:
        await _authenticate_oidc_with_cache(force)
