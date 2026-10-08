import asyncio
import contextlib
import os
from unittest.mock import MagicMock

import pytest
import requests
from mat3ra.api_client import ACCESS_TOKEN_ENV_VAR, AuthContext
from mat3ra.notebooks_utils import auth, token_store
from mat3ra.notebooks_utils.api.job import wait_for_jobs_to_finish_async
from mat3ra.notebooks_utils.core.api import token_store as file_token_store

POLL_INTERVAL_SECONDS = 0.01
CACHED_TOKEN_DATA = {"access_token": "cached-token", "expires_in": 3600}
NEW_TOKEN_DATA = {"access_token": "new-token", "expires_in": 3600}
FINISHED_JOBS = [{"status": "finished"}]
HTTP_ERROR_401 = requests.HTTPError(response=MagicMock(status_code=401))
HTTP_ERROR_403 = requests.HTTPError(response=MagicMock(status_code=403))
HTTP_ERROR_503 = requests.HTTPError(response=MagicMock(status_code=503))


async def completed_device_login(show_popup):
    auth.store_token_data_in_environment(NEW_TOKEN_DATA)
    return NEW_TOKEN_DATA


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_results", "expectation", "expected_access_token"),
    [
        ([asyncio.TimeoutError(), FINISHED_JOBS], contextlib.nullcontext(), "cached-token"),
        ([HTTP_ERROR_503, FINISHED_JOBS], contextlib.nullcontext(), "cached-token"),
        ([HTTP_ERROR_403, FINISHED_JOBS], pytest.raises(requests.HTTPError), "cached-token"),
        ([HTTP_ERROR_401, FINISHED_JOBS], contextlib.nullcontext(), "new-token"),
        ([HTTP_ERROR_401, HTTP_ERROR_401, FINISHED_JOBS], pytest.raises(requests.HTTPError), "new-token"),
    ],
)
async def test_wait_for_jobs_to_finish_async(monkeypatch, tmp_path, status_results, expectation, expected_access_token):
    monkeypatch.setattr(file_token_store, "_FILE_PATH", str(tmp_path / "oidc_token_cache.json"))
    monkeypatch.setattr(auth, "authenticate_oidc", completed_device_login)
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, CACHED_TOKEN_DATA["access_token"])
    auth_context = AuthContext(access_token=CACHED_TOKEN_DATA["access_token"])
    endpoint = MagicMock(auth=auth_context, list=MagicMock(side_effect=status_results))

    with expectation:
        await wait_for_jobs_to_finish_async(endpoint, ["job-1"], poll_interval=POLL_INTERVAL_SECONDS)
    assert auth_context.access_token == expected_access_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment_token", "token_check_error", "checked_token", "expected_token"),
    [
        ("", HTTP_ERROR_401, "cached-token", "new-token"),
        ("environment-token", KeyError("data"), "environment-token", "new-token"),
        ("", None, "cached-token", "cached-token"),
    ],
)
async def test_authenticate(monkeypatch, tmp_path, environment_token, token_check_error, checked_token, expected_token):
    monkeypatch.setattr(file_token_store, "_FILE_PATH", str(tmp_path / "oidc_token_cache.json"))
    monkeypatch.setattr(auth, "authenticate_oidc", completed_device_login)
    api_client = MagicMock()
    api_client.authenticate.return_value.list_accounts.side_effect = token_check_error
    monkeypatch.setattr(auth, "APIClient", api_client)
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, environment_token)
    await token_store.save_token(auth.get_oidc_base_url(), CACHED_TOKEN_DATA)

    await auth.authenticate(globals_dict={})

    assert os.environ[ACCESS_TOKEN_ENV_VAR] == expected_token
    api_client.authenticate.assert_called_once_with(access_token=checked_token)
