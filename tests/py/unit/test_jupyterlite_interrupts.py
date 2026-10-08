import asyncio
import contextlib
import threading
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.api.job import wait_for_jobs_to_finish_async
from mat3ra.notebooks_utils.core.api.auth import _poll_for_token_data
from mat3ra.notebooks_utils.pyodide.runtime import (
    UserAbortError,
    interruptible_polling_loop,
    run_interruptible_loop_async,
)

POLL_INTERVAL_SECONDS = 0.01
ABORT_AFTER_SECONDS = 0.05
BLOCKED_REQUEST_SECONDS = 1.0
TOKEN_DATA = {"access_token": "new-token", "expires_in": 3600}
PENDING_TOKEN_RESPONSE = MagicMock(status_code=400, json=MagicMock(return_value={"error": "authorization_pending"}))
AUTHORIZED_TOKEN_RESPONSE = MagicMock(status_code=200, json=MagicMock(return_value=TOKEN_DATA))
SERVER_ERROR_RESPONSE = MagicMock(status_code=502, json=MagicMock(side_effect=ValueError))
REFUSED_TOKEN_RESPONSE = MagicMock(status_code=400, json=MagicMock(return_value={"error": "access_denied"}))
DEVICE_FLOW_ARGUMENTS = ("https://platform.mat3ra.com/oidc", "client-1", "device-code-1", POLL_INTERVAL_SECONDS, 600)


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
    "start_polling",
    [
        lambda blocked_request: wait_for_jobs_to_finish_async(MagicMock(list=blocked_request), ["job-1"]),
        lambda blocked_request: _poll_for_token_data(*DEVICE_FLOW_ARGUMENTS),
    ],
)
async def test_abort_raises_user_abort_error_while_a_request_is_in_flight(monkeypatch, start_polling):
    release_request = threading.Event()

    def blocked_request(*args, **kwargs):
        release_request.wait(BLOCKED_REQUEST_SECONDS)

    monkeypatch.setattr("requests.post", blocked_request)
    task = asyncio.create_task(start_polling(blocked_request))
    await asyncio.sleep(ABORT_AFTER_SECONDS)
    task.cancel()
    with pytest.raises(UserAbortError):
        await task
    release_request.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_responses", "expectation"),
    [
        ([PENDING_TOKEN_RESPONSE, SERVER_ERROR_RESPONSE, AUTHORIZED_TOKEN_RESPONSE], contextlib.nullcontext()),
        ([REFUSED_TOKEN_RESPONSE], pytest.raises(Exception, match=r"\(400\): access_denied")),
    ],
)
async def test_poll_for_token_data(monkeypatch, token_responses, expectation):
    monkeypatch.setattr("requests.post", MagicMock(side_effect=token_responses))
    with expectation:
        assert await _poll_for_token_data(*DEVICE_FLOW_ARGUMENTS) == TOKEN_DATA


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
