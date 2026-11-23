import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from mat3ra.api_client import AuthContext, JobEndpoints
from mat3ra.notebooks_utils.core.entity.job.api import get_jobs_statuses_by_ids_async

OWNER_ID = "account-1"
JOB_PREFIX = "NEB H2+H"
CREATED_JOB: Dict[str, Any] = {"_id": "job-1", "name": JOB_PREFIX}

REQUEST_TIMEOUT_SECONDS = 0.05
BLOCKED_REQUEST_SECONDS = 1.0
ACCESS_TOKEN = "access-token-1"
ABORT_SIGNAL = "abort-signal"
JOBS_FETCH_URL = (
    "https://platform.mat3ra.com:443/api/2018-10-01/jobs"
    "?query=%7B%22_id%22%3A+%7B%22%24in%22%3A+%5B%22job-1%22%5D%7D%7D"
    "&projection=%7B%22fields%22%3A+%7B%22status%22%3A+1%7D%7D"
)
BEARER_HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_get_jobs_statuses_by_ids_async(monkeypatch):
    pyfetch = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(BLOCKED_REQUEST_SECONDS))
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.job.api.pyfetch", pyfetch)
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.job.api.is_pyodide_environment", lambda: True)
    endpoint = JobEndpoints("platform.mat3ra.com", 443, OWNER_ID, None, auth=AuthContext(access_token=ACCESS_TOKEN))

    with pytest.raises(asyncio.TimeoutError):
        await get_jobs_statuses_by_ids_async(endpoint, [CREATED_JOB["_id"]], REQUEST_TIMEOUT_SECONDS, ABORT_SIGNAL)
    pyfetch.assert_called_once_with(JOBS_FETCH_URL, headers=BEARER_HEADERS, signal=ABORT_SIGNAL)
