import asyncio
import os
import time
import urllib.parse
from typing import Any, Awaitable, Callable, Optional

import requests
from mat3ra.api_client import ACCESS_TOKEN_ENV_VAR, CLIENT_ID, SCOPE, APIEnv, build_oidc_base_url

from ...primitive.environment import is_pyodide_environment
from ...pyodide.runtime import run_interruptible_loop_async

try:
    from pyodide.http import pyfetch  # type: ignore
except ImportError:
    pyfetch = None

REFRESH_TOKEN_ENV_VAR = "OIDC_REFRESH_TOKEN"
TOKEN_REQUEST_TIMEOUT_SECONDS = 10
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}
PENDING_LOGIN_ERRORS = ("authorization_pending", "slow_down")


def get_oidc_base_url() -> str:
    env = APIEnv.from_env()
    return build_oidc_base_url(env.host, env.port, env.secure)


def request_device_flow_state(oidc_base_url: str, client_id: str, scope: str) -> dict:
    """
    Request an OAuth/OIDC Device Authorization flow state.

    Args:
        oidc_base_url: Base OIDC URL.
        client_id: OAuth client identifier for the device flow.
        scope: Space-separated scopes to request (e.g. "openid profile email").

    Returns:
        A dict with device_code, user_code, verification_uri_complete,
        polling_interval_seconds, expires_in_seconds.
    """
    device_response = requests.post(
        f"{oidc_base_url}/device/auth",
        data={"client_id": client_id, "scope": scope},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    device_response.raise_for_status()
    device_data = device_response.json()
    return {
        "device_code": device_data["device_code"],
        "user_code": device_data["user_code"],
        "verification_uri_complete": device_data.get("verification_uri_complete", device_data["verification_uri"]),
        "polling_interval_seconds": int(device_data.get("interval", 5)),
        "expires_in_seconds": int(device_data.get("expires_in", 600)),
    }


def store_token_data_in_environment(token_data: dict) -> None:
    os.environ[ACCESS_TOKEN_ENV_VAR] = token_data["access_token"]
    if "refresh_token" in token_data:
        os.environ[REFRESH_TOKEN_ENV_VAR] = token_data["refresh_token"]


def _get_token_data(status_code: int, response_data: dict) -> dict:
    """
    Token data of a token response, empty while the login is pending or after a server error (5xx), which is polled
    again; raises with the status and the error code when the login was refused.
    """
    if status_code == 200:
        return response_data
    if status_code >= 500 or response_data.get("error") in PENDING_LOGIN_ERRORS:
        return {}
    raise Exception(f"Device login failed ({status_code}): {response_data.get('error')}.")


def _request_token_data(token_url: str, form_data: dict) -> dict:
    response = requests.post(token_url, data=form_data, headers=FORM_HEADERS, timeout=TOKEN_REQUEST_TIMEOUT_SECONDS)
    return _get_token_data(response.status_code, response.json() if response.status_code < 500 else {})


async def _request_token_data_with_fetch(token_url: str, form_data: dict, abort_signal: Any) -> dict:
    """
    `_request_token_data` through the browser's fetch, which leaves the event loop free while the request is in flight.
    """
    body = urllib.parse.urlencode(form_data, doseq=True)
    response = await pyfetch(token_url, method="POST", body=body, headers=FORM_HEADERS, signal=abort_signal)
    return _get_token_data(response.status, await response.json() if response.status < 500 else {})


async def _poll_for_token_data(
    oidc_base_url: str,
    client_id: str,
    device_code: str,
    polling_interval_seconds: int,
    expires_in_seconds: int,
) -> dict:
    """Polls for the token until the device login is confirmed; in pyodide, ESC stops it at once."""
    token_url = f"{oidc_base_url}/token"
    form_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": client_id,
        "redirect_uris": [],
        "response_types": [],
        "token_endpoint_auth_method": "none",
    }
    deadline_seconds = time.time() + expires_in_seconds
    token_data: dict = {}

    def request_token_data(abort_signal: Any) -> Awaitable[dict]:
        if is_pyodide_environment():
            return _request_token_data_with_fetch(token_url, form_data, abort_signal)
        return asyncio.get_running_loop().run_in_executor(None, _request_token_data, token_url, form_data)

    async def poll_step(abort_signal: Any) -> bool:
        if time.time() >= deadline_seconds:
            raise Exception("Timeout waiting for authorization.")
        token_data.update(await asyncio.wait_for(request_token_data(abort_signal), TOKEN_REQUEST_TIMEOUT_SECONDS))
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
