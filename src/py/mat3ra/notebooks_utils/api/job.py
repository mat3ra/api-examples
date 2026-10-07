import asyncio
import datetime
from collections import Counter
from typing import Any, List

import requests
from mat3ra.api_client import JobEndpoints
from mat3ra.utils.extra.tabulate import pretty_print

from ..core.entity.job.api import create_job, get_jobs_statuses_by_ids_async, save_files, submit_jobs
from ..pyodide.runtime import interruptible_polling_loop


# Contains no external dependencies, only uses the API client,
# so can be used in both regular Python and Pyodide environments.
@interruptible_polling_loop()
async def wait_for_jobs_to_finish_async(
    endpoint: JobEndpoints, job_ids: List[str], *, abort_signal: Any = None
) -> bool:
    """
    Waits for jobs to finish and prints their statuses.
    A job is considered finished if it is not in "pre-submission", "submitted", or "active" status.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client
        job_ids (list): list of job IDs to wait for
        abort_signal: JS AbortSignal of the Abort control, passed in by the polling loop
    """
    try:
        statuses = await get_jobs_statuses_by_ids_async(endpoint, job_ids, abort_signal=abort_signal)
    except (asyncio.TimeoutError, OSError) as error:
        if isinstance(error, requests.HTTPError) and error.response.status_code < 500:
            raise
        print(f"{datetime.datetime.now():%Y-%m-%d-%H:%M:%S} status check failed: {error!r}, retrying")
        return True
    counts = Counter(statuses)
    headers = ["TIME", "SUBMITTED-JOBS", "ACTIVE-JOBS", "FINISHED-JOBS", "ERRORED-JOBS"]
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    row = [
        now,
        counts.get("submitted", 0) + counts.get("queued", 0),
        counts.get("active", 0),
        counts.get("finished", 0),
        counts.get("error", 0),
    ]
    pretty_print([row], headers, tablefmt="grid", stralign="center")

    active_statuses = {"pre-submission", "submitted", "queued", "active"}
    return not statuses or any(status in active_statuses for status in statuses)


__all__ = [
    "create_job",
    "save_files",
    "submit_jobs",
    "wait_for_jobs_to_finish_async",
]
