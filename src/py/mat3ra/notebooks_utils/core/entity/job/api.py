import asyncio
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Dict, Iterable, List, Optional, Union

import requests
from mat3ra.api_client import APIClient, JobEndpoints

from ....auth import reauthenticate
from ....primitive.environment import is_pyodide_environment

try:
    from pyodide.http import pyfetch  # type: ignore
except ImportError:
    pyfetch = None

MATERIALS_SET_ENTITY_CLASS = "Material"
DEFAULT_STATUS_TIMEOUT_SECONDS = 30


def save_files(job_id: str, job_endpoint: JobEndpoints, filename_on_cloud: str, filename_on_disk: str) -> None:
    """
    Saves a file to disk, overwriting any files with the same name as filename_on_disk.

    Args:
        job_id (str): ID of the job
        job_endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client
        filename_on_cloud (str): Name of the file on the server
        filename_on_disk (str): Name the file will be saved to
    """
    files = job_endpoint.list_files(job_id)
    file_metadata = next(f for f in files if filename_on_cloud in f["key"])
    signed_url = file_metadata["signedUrl"]
    server_response = urllib.request.urlopen(signed_url)
    with open(filename_on_disk, "wb") as outp:
        outp.write(server_response.read())


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


def _materials_set_reference(materials_set: Dict[str, Any]) -> Dict[str, str]:
    """
    Builds the `_materialsSet` reference a job config expects.

    Mirrors what the job designer sends: the set's ID, the entity class it holds,
    and a slug. The platform resolves members from the ID, so `slug` is only a
    label — falling back to `name` keeps it readable when the response omits it.

    Args:
        materials_set (dict): Materials set document.

    Returns:
        dict: The `_materialsSet` reference.

    Raises:
        KeyError: If the set document carries neither `slug` nor `name`.
    """
    slug = materials_set.get("slug") or materials_set.get("name")
    if not slug:
        raise KeyError(f"Materials set {materials_set['_id']} has neither 'slug' nor 'name'.")
    return {
        "_id": materials_set["_id"],
        "cls": MATERIALS_SET_ENTITY_CLASS,
        "slug": slug,
    }


def create_job(
    api_client: APIClient,
    materials: List[dict],
    workflow: dict,
    project_id: str,
    owner_id: str,
    prefix: str,
    compute: Optional[dict] = None,
    materials_set: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Union[dict, List[dict]]:
    """
    Creates jobs using pre-serialised material and workflow dicts.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        materials (list[dict]): Serialised material dicts.
        workflow (dict): Serialised workflow dict.
        project_id (str): Project ID.
        owner_id (str): Account ID.
        prefix (str): Job name prefix.
        compute (dict, optional): Compute configuration dict.
        materials_set (dict, optional): Ordered/unordered materials set document
            (same contract as the job designer `_materialsSet`).
        tags (list[str], optional): Job tags, e.g. ["charge:-1"].

    Returns:
        dict | list[dict]: Created job(s).
    """
    workflow.pop("_id", None)
    is_multimaterial = workflow.get("isMultiMaterial", False)

    config: dict = {
        "_project": {"_id": project_id},
        "workflow": workflow,
        "owner": {"_id": owner_id},
        "name": prefix,
        "_material": {"_id": materials[0]["_id"]},
    }

    if is_multimaterial:
        config["_materials"] = [{"_id": m["_id"]} for m in materials]

    if materials_set is not None:
        config["_materialsSet"] = _materials_set_reference(materials_set)

    if compute:
        config["compute"] = compute

    if tags:
        config["tags"] = list(tags)

    return api_client.jobs.create(config)


def find_job_for_material(
    api_client: APIClient,
    material_id: str,
    workflow_name: str,
    owner_id: str,
    statuses: Iterable[str] = ("finished",),
    kgrid: Optional[List[int]] = None,
    unit_name: str = "pw_scf",
) -> Optional[dict]:
    """
    Finds a job for a material and workflow name under the given owner, filtered by status and,
    optionally, by the k-grid its `unit_name` unit ran on.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        material_id (str): The job's `_material._id`.
        workflow_name (str): Exact workflow name the job was created with.
        owner_id (str): Account ID the job must belong to.
        statuses (Iterable[str]): Job statuses that count as a match.
        kgrid (List[int], optional): Exact k-grid dimensions the job's `unit_name` unit ran on; None for no condition.
        unit_name (str): Name of the unit the k-grid was set on.

    Returns:
        dict, optional: The matching job, or None if none exists.
    """
    existing = api_client.jobs.list(
        {
            "_material._id": material_id,
            "owner._id": owner_id,
            "workflow.name": workflow_name,
            "status": {"$in": list(statuses)},
            **get_kgrid_query(kgrid, unit_name),
        },
        {"limit": 1},
    )
    return existing[0] if existing else None


def get_kgrid_query(kgrid: Optional[List[int]], unit_name: str = "pw_scf") -> Dict[str, Any]:
    """
    `jobs.list` condition for jobs whose `unit_name` unit ran on `kgrid` (empty when `kgrid` is None), matched where
    `apply_scf_kgrid` sets it: `workflow.subworkflows[].units[name].context[name="kgrid"].data.dimensions`.
    A job created without an explicit k-grid has no such context and never matches.
    """
    if kgrid is None:
        return {}
    kgrid_context = {"$elemMatch": {"name": "kgrid", "data.dimensions": list(kgrid)}}
    return {"workflow.subworkflows.units": {"$elemMatch": {"name": unit_name, "context": kgrid_context}}}


def get_kgrid_of_job(job: Dict[str, Any], unit_name: str = "pw_scf") -> Optional[List[int]]:
    """
    K-grid dimensions the job's `unit_name` unit ran on: its `kgrid` context, or, for a job created without one, the
    grid the platform rendered into the unit's input, `workflow.subworkflows[].units[name].input[0].rendered`.
    """
    units = [unit for subworkflow in job["workflow"]["subworkflows"] for unit in subworkflow["units"]]
    unit = next(unit for unit in units if unit["name"] == unit_name)
    kgrid_context = next((item for item in unit["context"] if item["name"] == "kgrid"), None)
    if kgrid_context:
        return kgrid_context["data"]["dimensions"]
    match = re.search(r"K_POINTS automatic\s+(\d+)\s+(\d+)\s+(\d+)", unit["input"][0]["rendered"])
    return [int(dimension) for dimension in match.groups()] if match else None


def find_job_for_material_with_property(
    api_client: APIClient,
    material_id: str,
    property_name: str,
    owner_id: str,
    tags: Optional[List[str]] = None,
    kgrid: Optional[List[int]] = None,
) -> Optional[dict]:
    """
    Finds a finished job on a material that reported the given property, optionally among the jobs
    carrying every one of `tags` (e.g. ["charge:0"] for a reference computed in the neutral state)
    and among those whose `pw_scf` unit ran on `kgrid`.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        material_id (str): The job's `_material._id`.
        property_name (str): Property the job must have reported, e.g. "total_energy".
        owner_id (str): Account ID the job must belong to.
        tags (List[str], optional): Tags the job must all carry.
        kgrid (List[int], optional): Exact k-grid dimensions the job's `pw_scf` unit ran on; None for no condition.

    Returns:
        dict, optional: The first matching job, or None if none exists.
    """
    query: Dict[str, Any] = {"_material._id": material_id, "owner._id": owner_id, "status": "finished"}
    if tags:
        query["tags"] = {"$all": list(tags)}
    jobs = api_client.jobs.list({**query, **get_kgrid_query(kgrid)})
    return next(
        (job for job in jobs if api_client.properties.get_for_job(job["_id"], property_name=property_name)), None
    )


def submit_jobs(endpoint: JobEndpoints, job_ids: List[str]) -> None:
    """
    Submits jobs by IDs.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client.
        job_ids (list[str]): Job IDs to submit.
    """
    for job_id in job_ids:
        endpoint.submit(job_id)
