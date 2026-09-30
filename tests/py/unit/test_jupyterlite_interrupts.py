import asyncio
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.api.job import wait_for_jobs_to_finish_async
from mat3ra.notebooks_utils.pyodide.runtime import (
    UserAbortError,
    interruptible_polling_loop,
    run_interruptible_loop_async,
)

POLL_INTERVAL_SECONDS = 0.01
ABORT_AFTER_SECONDS = 0.05
ABORT_DEADLINE_SECONDS = 0.2
BLOCKED_REQUEST_SECONDS = 1.0
READ_ABORT_CHANNEL_NAME = (
    "from mat3ra.notebooks_utils.pyodide.runtime import ABORT_CHANNEL_NAME; print(ABORT_CHANNEL_NAME)"
)


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


def test_abort_channel_name_differs_per_kernel():
    channel_names = {
        subprocess.run([sys.executable, "-c", READ_ABORT_CHANNEL_NAME], capture_output=True, text=True).stdout
        for _ in range(2)
    }
    assert len(channel_names) == 2
    assert all(channel_name.startswith("mat3ra_abort_") for channel_name in channel_names)


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
