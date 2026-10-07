import asyncio
import contextlib
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from mat3ra.notebooks_utils.api.job import wait_for_jobs_to_finish_async
from mat3ra.notebooks_utils.core.api.auth import _poll_for_token_data
from mat3ra.notebooks_utils.pyodide.runtime import (
    BroadcastChannelAbortController,
    UserAbortError,
    interruptible_polling_loop,
    run_interruptible_loop_async,
)

POLL_INTERVAL_SECONDS = 0.01
ABORT_AFTER_SECONDS = 0.05
ABORT_DEADLINE_SECONDS = 0.2
BLOCKED_REQUEST_SECONDS = 1.0


@pytest.mark.asyncio
async def test_run_interruptible_loop_async_stops_when_body_returns_false():
    call_count = 0

    async def loop_body(abort_signal):
        nonlocal call_count
        call_count += 1
        return call_count < 3

    await run_interruptible_loop_async(
        loop_body,
        POLL_INTERVAL_SECONDS,
        show_controls=False,
    )
    assert call_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("poll_seconds", "poll_interval_seconds"),
    [(10.0, POLL_INTERVAL_SECONDS), (0.0, 10.0)],
    ids=["during a poll", "during the sleep"],
)
async def test_run_interruptible_loop_async_raises_user_abort_error_when_cancelled(poll_seconds, poll_interval_seconds):
    async def loop_body(abort_signal):
        await asyncio.sleep(poll_seconds)
        return True

    task = asyncio.create_task(run_interruptible_loop_async(loop_body, poll_interval_seconds, show_controls=False))
    await asyncio.sleep(ABORT_AFTER_SECONDS)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(UserAbortError):
        await task
    assert time.monotonic() - started < ABORT_DEADLINE_SECONDS


@pytest.mark.asyncio
async def test_wait_for_jobs_to_finish_async_raises_user_abort_error_while_the_status_request_blocks():
    release_request = threading.Event()

    def list_jobs(query, projection):
        release_request.wait(BLOCKED_REQUEST_SECONDS)
        return [{"status": "finished"}]

    endpoint = MagicMock()
    endpoint.list.side_effect = list_jobs
    started = time.monotonic()
    task = asyncio.create_task(wait_for_jobs_to_finish_async(endpoint, ["job-1"], poll_interval=POLL_INTERVAL_SECONDS))
    await asyncio.sleep(ABORT_AFTER_SECONDS)
    task.cancel()
    with pytest.raises(UserAbortError):
        await task
    release_request.set()
    assert time.monotonic() - started < ABORT_DEADLINE_SECONDS


HTTP_ERROR_503 = requests.HTTPError("Error 503.", response=MagicMock(status_code=503))
HTTP_ERROR_403 = requests.HTTPError("Error 403.", response=MagicMock(status_code=403))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_results", "expectation"),
    [
        ([asyncio.TimeoutError(), ["finished"]], contextlib.nullcontext()),
        ([requests.ConnectionError(), OSError("Failed to fetch"), ["finished"]], contextlib.nullcontext()),
        ([HTTP_ERROR_503, ["finished"]], contextlib.nullcontext()),
        ([HTTP_ERROR_403], pytest.raises(requests.HTTPError)),
    ],
    ids=["timeout", "network error", "503", "403"],
)
async def test_wait_for_jobs_to_finish_async(monkeypatch, capsys, status_results, expectation):
    get_statuses = AsyncMock(side_effect=status_results)
    monkeypatch.setattr("mat3ra.notebooks_utils.api.job.get_jobs_statuses_by_ids_async", get_statuses)

    with expectation:
        await wait_for_jobs_to_finish_async(MagicMock(), ["job-1"], poll_interval=POLL_INTERVAL_SECONDS)
    assert get_statuses.await_count == len(status_results)
    assert capsys.readouterr().out.count("retrying") == len(status_results) - 1


@pytest.mark.asyncio
async def test_wait_for_jobs_to_finish_async_raises_user_abort_error_after_an_aborted_fetch(monkeypatch):
    monkeypatch.setattr(BroadcastChannelAbortController, "start", lambda self, task: setattr(self, "is_aborted", True))
    get_statuses = AsyncMock(side_effect=[OSError("The user aborted a request.")])
    monkeypatch.setattr("mat3ra.notebooks_utils.api.job.get_jobs_statuses_by_ids_async", get_statuses)

    with pytest.raises(UserAbortError):
        await wait_for_jobs_to_finish_async(MagicMock(), ["job-1"], poll_interval=10.0)
    assert get_statuses.await_count == 1


TOKEN_DATA = {"access_token": "new-token", "expires_in": 3600}
PENDING_TOKEN_RESPONSE = MagicMock(status_code=400, json=MagicMock(return_value={"error": "authorization_pending"}))
AUTHORIZED_TOKEN_RESPONSE = MagicMock(status_code=200, json=MagicMock(return_value=TOKEN_DATA))
SLOW_DOWN_TOKEN_RESPONSE = MagicMock(status_code=400, json=MagicMock(return_value={"error": "slow_down"}))
REFUSED_TOKEN_RESPONSE = MagicMock(status_code=400, json=MagicMock(return_value={"error": "access_denied"}))
SERVER_ERROR_RESPONSE = MagicMock(status_code=502, json=MagicMock(side_effect=ValueError("not JSON")))
DEVICE_FLOW_ARGUMENTS = ("https://platform.mat3ra.com/oidc", "client-1", "device-code-1")
EXPIRES_IN_SECONDS = 600


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_responses", "expires_in_seconds", "expectation", "expected_token_data"),
    [
        ([PENDING_TOKEN_RESPONSE, AUTHORIZED_TOKEN_RESPONSE], EXPIRES_IN_SECONDS, contextlib.nullcontext(), TOKEN_DATA),
        ([SLOW_DOWN_TOKEN_RESPONSE], POLL_INTERVAL_SECONDS, pytest.raises(Exception, match="Timeout"), None),
        ([REFUSED_TOKEN_RESPONSE], EXPIRES_IN_SECONDS, pytest.raises(Exception, match="access_denied"), None),
        ([SERVER_ERROR_RESPONSE, AUTHORIZED_TOKEN_RESPONSE], EXPIRES_IN_SECONDS, contextlib.nullcontext(), TOKEN_DATA),
    ],
    ids=["authorized on the 2nd poll", "slowed down until expiry", "login refused", "authorized after a 502"],
)
async def test_poll_for_token_data(monkeypatch, token_responses, expires_in_seconds, expectation, expected_token_data):
    monkeypatch.setattr("requests.post", MagicMock(side_effect=token_responses))

    with expectation:
        token_data = await _poll_for_token_data(*DEVICE_FLOW_ARGUMENTS, POLL_INTERVAL_SECONDS, expires_in_seconds)
        assert token_data == expected_token_data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_seconds", "poll_interval_seconds", "response"),
    [(BLOCKED_REQUEST_SECONDS, POLL_INTERVAL_SECONDS, AUTHORIZED_TOKEN_RESPONSE), (0.0, 10.0, PENDING_TOKEN_RESPONSE)],
    ids=["during the token request", "during the sleep"],
)
async def test_poll_for_token_data_raises_user_abort(monkeypatch, request_seconds, poll_interval_seconds, response):
    release_request = threading.Event()

    def post_token_request(*args, **kwargs):
        release_request.wait(request_seconds)
        return response

    monkeypatch.setattr("requests.post", post_token_request)
    started = time.monotonic()
    task = asyncio.create_task(_poll_for_token_data(*DEVICE_FLOW_ARGUMENTS, poll_interval_seconds, EXPIRES_IN_SECONDS))
    await asyncio.sleep(ABORT_AFTER_SECONDS)
    task.cancel()
    with pytest.raises(UserAbortError):
        await task
    release_request.set()
    assert time.monotonic() - started < ABORT_DEADLINE_SECONDS


@pytest.mark.asyncio
async def test_interruptible_polling_loop_decorator_returns_coroutine_and_runs_until_false():
    call_count = 0

    @interruptible_polling_loop(show_controls=False)
    def poll_step(abort_signal):
        nonlocal call_count
        call_count += 1
        return call_count < 2

    assert asyncio.iscoroutinefunction(poll_step)
    await poll_step(poll_interval=POLL_INTERVAL_SECONDS)
    assert call_count == 2


def test_user_abort_error_is_runtime_error():
    error = UserAbortError("test message")
    assert isinstance(error, RuntimeError)
    assert str(error) == "test message"
