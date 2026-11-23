import asyncio
import time
import urllib.parse
from typing import Any, Awaitable, Callable, Optional

from mat3ra.api_client import CLIENT_ID, SCOPE
from mat3ra.api_client.tools.auth import (
    FORM_HEADERS,
    REFRESH_TOKEN_ENV_VAR,
    TOKEN_REQUEST_TIMEOUT_SECONDS,
    get_oidc_base_url,
    get_token_data_from_response,
    get_token_request_form_data,
    request_device_flow_state,
    request_token_data,
    store_token_data_in_environment,
)

from ...primitive.environment import is_pyodide_environment
from ...pyodide.runtime import run_interruptible_loop_async

try:
    from pyodide.http import pyfetch  # type: ignore
except ImportError:
    pyfetch = None


async def _request_token_data_with_fetch(token_url: str, form_data: dict, abort_signal: Any) -> dict:
    """
    `request_token_data` through the browser's fetch, which leaves the event loop free while the request is in flight.
    """
    body = urllib.parse.urlencode(form_data, doseq=True)
    response = await pyfetch(token_url, method="POST", body=body, headers=FORM_HEADERS, signal=abort_signal)
    return get_token_data_from_response(response.status, await response.json() if response.status < 500 else {})


async def _poll_for_token_data(
    oidc_base_url: str,
    client_id: str,
    device_code: str,
    polling_interval_seconds: int,
    expires_in_seconds: int,
) -> dict:
    """Polls for the token until the device login is confirmed; in pyodide, ESC stops it at once."""
    token_url = f"{oidc_base_url}/token"
    form_data = get_token_request_form_data(client_id, device_code)
    deadline_seconds = time.time() + expires_in_seconds
    token_data: dict = {}

    def request_token_data_async(abort_signal: Any) -> Awaitable[dict]:
        if is_pyodide_environment():
            return _request_token_data_with_fetch(token_url, form_data, abort_signal)
        return asyncio.get_running_loop().run_in_executor(None, request_token_data, token_url, form_data)

    async def poll_step(abort_signal: Any) -> bool:
        if time.time() >= deadline_seconds:
            raise Exception("Timeout waiting for authorization.")
        token_data.update(await asyncio.wait_for(request_token_data_async(abort_signal), TOKEN_REQUEST_TIMEOUT_SECONDS))
        return not token_data

    await run_interruptible_loop_async(
        poll_step, polling_interval_seconds, show_button=False, abort_hint_text="Press ESC to cancel"
    )
    return token_data


async def authenticate_oidc(
    oidc_base_url: Optional[str] = None,
    client_id: str = CLIENT_ID,
    scope: str = SCOPE,
    show_popup: Optional[Callable[[str, str], None]] = None,
) -> dict:
    if oidc_base_url is None:
        oidc_base_url = get_oidc_base_url()
    device_flow_state = request_device_flow_state(oidc_base_url, client_id, scope)
    if show_popup is not None:
        show_popup(device_flow_state["verification_uri_complete"], device_flow_state["user_code"])
    token_data = await _poll_for_token_data(
        oidc_base_url=oidc_base_url,
        client_id=client_id,
        device_code=device_flow_state["device_code"],
        polling_interval_seconds=device_flow_state["polling_interval_seconds"],
        expires_in_seconds=device_flow_state["expires_in_seconds"],
    )
    store_token_data_in_environment(token_data)
    return token_data


__all__ = [
    "FORM_HEADERS",
    "REFRESH_TOKEN_ENV_VAR",
    "TOKEN_REQUEST_TIMEOUT_SECONDS",
    "authenticate_oidc",
    "get_oidc_base_url",
    "request_device_flow_state",
    "store_token_data_in_environment",
]
