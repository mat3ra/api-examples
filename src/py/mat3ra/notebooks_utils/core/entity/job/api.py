import asyncio
import json
import urllib.parse
from typing import Any, Awaitable, List

import requests
from mat3ra.api_client import JobEndpoints
from mat3ra.api_client.tools.job import (
    MATERIALS_SET_ENTITY_CLASS,
    create_job,
    find_job_for_material,
    find_job_for_material_with_property,
    get_kgrid_of_job,
    get_kgrid_query,
    save_files,
    submit_jobs,
)

from ....auth import reauthenticate
from ....primitive.environment import is_pyodide_environment

try:
    from pyodide.http import pyfetch  # type: ignore
except ImportError:
    pyfetch = None

DEFAULT_STATUS_TIMEOUT_SECONDS = 30


async def _list_jobs_with_fetch(endpoint: JobEndpoints, query: dict, projection: dict, abort_signal: Any) -> List[dict]:
    """
    `endpoint.list` through the browser's fetch, which leaves the event loop free while the request is in flight.
    Raises `requests.HTTPError` on an error status.
    """
    parameters = urllib.parse.urlencode({"query": json.dumps(query), "projection": json.dumps(projection)})
    url = urllib.parse.urljoin(endpoint.conn.preamble, f"{endpoint.name}?{parameters}")
    response = await pyfetch(url, headers={**endpoint.headers, **endpoint.auth.get_headers()}, signal=abort_signal)
    if not response.ok:
        error_response = requests.Response()
        error_response.status_code = response.status
        raise requests.HTTPError(f"Error {response.status}.", response=error_response)
    return (await response.json())["data"]


async def get_jobs_statuses_by_ids_async(
    endpoint: JobEndpoints,
    job_ids: List[str],
    timeout: float = DEFAULT_STATUS_TIMEOUT_SECONDS,
    abort_signal: Any = None,
) -> List[str]:
    """
    Gets jobs statuses by their IDs without blocking the event loop: through the browser's fetch in pyodide,
    in a worker thread otherwise. A rejected access token (401) is replaced through the device login once.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client
        job_ids (list): list of job IDs to get the status for
        timeout (float): seconds to wait for the response before raising asyncio.TimeoutError
        abort_signal: JS AbortSignal that aborts the fetch in pyodide

    Returns:
        list: list of job statuses
    """
    query = {"_id": {"$in": job_ids}}
    projection = {"fields": {"status": 1}}

    def request_jobs() -> Awaitable[List[dict]]:
        if is_pyodide_environment():
            return _list_jobs_with_fetch(endpoint, query, projection, abort_signal)
        return asyncio.get_running_loop().run_in_executor(None, endpoint.list, query, projection)

    try:
        jobs = await asyncio.wait_for(request_jobs(), timeout)
    except requests.HTTPError as error:
        if error.response.status_code != 401 or not endpoint.auth.access_token:
            raise
        await reauthenticate(endpoint.auth)
        jobs = await asyncio.wait_for(request_jobs(), timeout)
    return [job["status"] for job in jobs]


__all__ = [
    "DEFAULT_STATUS_TIMEOUT_SECONDS",
    "MATERIALS_SET_ENTITY_CLASS",
    "create_job",
    "find_job_for_material",
    "find_job_for_material_with_property",
    "get_jobs_statuses_by_ids_async",
    "get_kgrid_of_job",
    "get_kgrid_query",
    "save_files",
    "submit_jobs",
]
