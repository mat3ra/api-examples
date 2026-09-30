import contextlib
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from mat3ra.api_client import ACCESS_TOKEN_ENV_VAR, AuthContext
from mat3ra.notebooks_utils import auth, token_store
from mat3ra.notebooks_utils.core.api import token_store as file_token_store

STALE_TOKEN_DATA = {"access_token": "stale-token", "expires_in": 3600}
NEW_TOKEN_DATA = {"access_token": "new-token", "expires_in": 3600}
HTTP_ERROR_401 = requests.HTTPError("Error 401.", response=MagicMock(status_code=401))
HTTP_ERROR_500 = requests.HTTPError("Error 500.", response=MagicMock(status_code=500))
MISSING_DATA_ERROR = KeyError("data")


async def completed_device_login(show_popup):
    auth.store_token_data_in_environment(NEW_TOKEN_DATA)
    return NEW_TOKEN_DATA


async def abandoned_device_login(show_popup):
    raise TimeoutError("Timeout waiting for authorization.")


async def store_token_in_cache(monkeypatch):
    await token_store.save_token(auth.get_oidc_base_url(), STALE_TOKEN_DATA)


async def store_token_in_environment(monkeypatch):
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, STALE_TOKEN_DATA["access_token"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_login", "expectation", "expected_access_token", "expected_stored_access_token"),
    [
        (completed_device_login, contextlib.nullcontext(), "new-token", "new-token"),
        (abandoned_device_login, pytest.raises(TimeoutError), "stale-token", None),
    ],
    ids=["login completed", "login abandoned"],
)
async def test_reauthenticate(
    monkeypatch, tmp_path, device_login, expectation, expected_access_token, expected_stored_access_token
):
    monkeypatch.setattr(file_token_store, "_FILE_PATH", str(tmp_path / "oidc_token_cache.json"))
    monkeypatch.setattr(auth, "authenticate_oidc", device_login)
    monkeypatch.setattr(auth, "APIClient", MagicMock())
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, STALE_TOKEN_DATA["access_token"])
    oidc_base_url = auth.get_oidc_base_url()
    await token_store.save_token(oidc_base_url, STALE_TOKEN_DATA)
    auth_context = AuthContext(access_token=STALE_TOKEN_DATA["access_token"])

    with expectation:
        await auth.reauthenticate(auth_context)

    assert auth_context.access_token == expected_access_token
    assert os.environ.get(ACCESS_TOKEN_ENV_VAR) == expected_stored_access_token
    assert (await file_token_store.read()).get(oidc_base_url, {}).get("access_token") == expected_stored_access_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("store_token", "accounts_side_effect", "expectation", "expected_access_token", "expected_logins"),
    [
        (store_token_in_cache, HTTP_ERROR_401, contextlib.nullcontext(), "new-token", 1),
        (store_token_in_cache, MISSING_DATA_ERROR, contextlib.nullcontext(), "new-token", 1),
        (store_token_in_environment, HTTP_ERROR_401, contextlib.nullcontext(), "new-token", 1),
        (store_token_in_cache, None, contextlib.nullcontext(), "stale-token", 0),
        (store_token_in_environment, None, contextlib.nullcontext(), "stale-token", 0),
        (store_token_in_cache, HTTP_ERROR_500, pytest.raises(requests.HTTPError), None, 0),
    ],
    ids=[
        "cached token rejected",
        "cached token rejected in a 200 response body",
        "environment token rejected",
        "cached token accepted",
        "environment token accepted",
        "platform error",
    ],
)
async def test_authenticate(
    monkeypatch, tmp_path, store_token, accounts_side_effect, expectation, expected_access_token, expected_logins
):
    monkeypatch.setattr(file_token_store, "_FILE_PATH", str(tmp_path / "oidc_token_cache.json"))
    device_login = AsyncMock(side_effect=completed_device_login)
    monkeypatch.setattr(auth, "authenticate_oidc", device_login)
    api_client = MagicMock()
    api_client.authenticate.return_value.list_accounts.side_effect = accounts_side_effect
    monkeypatch.setattr(auth, "APIClient", api_client)
    monkeypatch.delenv(ACCESS_TOKEN_ENV_VAR, raising=False)
    await store_token(monkeypatch)

    with expectation:
        await auth.authenticate(globals_dict={})

    assert os.environ.get(ACCESS_TOKEN_ENV_VAR) == expected_access_token
    assert device_login.await_count == expected_logins
    api_client.authenticate.assert_called_once_with(access_token=STALE_TOKEN_DATA["access_token"])
