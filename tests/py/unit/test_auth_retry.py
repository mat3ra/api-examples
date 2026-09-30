import contextlib

import pytest
from mat3ra.api_client import ACCESS_TOKEN_ENV_VAR, AuthContext
from mat3ra.notebooks_utils import auth, token_store
from mat3ra.notebooks_utils.core.api import token_store as file_token_store

STALE_TOKEN_DATA = {"access_token": "stale-token", "expires_in": 3600}
NEW_TOKEN_DATA = {"access_token": "new-token", "expires_in": 3600}


async def completed_device_login(show_popup):
    auth.store_token_data_in_environment(NEW_TOKEN_DATA)
    return NEW_TOKEN_DATA


async def abandoned_device_login(show_popup):
    raise TimeoutError("Timeout waiting for authorization.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_login", "expectation", "expected_access_token", "expected_cached_access_token"),
    [
        (completed_device_login, contextlib.nullcontext(), "new-token", "new-token"),
        (abandoned_device_login, pytest.raises(TimeoutError), "stale-token", None),
    ],
    ids=["login completed", "login abandoned"],
)
async def test_reauthenticate(
    monkeypatch, tmp_path, device_login, expectation, expected_access_token, expected_cached_access_token
):
    monkeypatch.setattr(file_token_store, "_FILE_PATH", str(tmp_path / "oidc_token_cache.json"))
    monkeypatch.setattr(auth, "authenticate_oidc", device_login)
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, STALE_TOKEN_DATA["access_token"])
    oidc_base_url = auth.get_oidc_base_url()
    await token_store.save_token(oidc_base_url, STALE_TOKEN_DATA)
    auth_context = AuthContext(access_token=STALE_TOKEN_DATA["access_token"])

    with expectation:
        await auth.reauthenticate(auth_context)

    assert auth_context.access_token == expected_access_token
    assert (await file_token_store.read()).get(oidc_base_url, {}).get("access_token") == expected_cached_access_token
