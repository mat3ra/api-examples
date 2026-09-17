import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from mat3ra.api_client import APIClient, JobEndpoints
from mat3ra.wode import Workflow

MATERIALS_SET_ENTITY_CLASS = "Material"


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


def get_jobs_statuses_by_ids(endpoint: JobEndpoints, job_ids: List[str]) -> List[str]:
    """
    Gets jobs statues by their IDs.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client
        job_ids (list): list of job IDs to get the status for

    Returns:
        list: list of job statuses
    """
    jobs = endpoint.list({"_id": {"$in": job_ids}}, {"fields": {"status": 1}})
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
) -> dict:
    """
    Creates a job using pre-serialised material and workflow dicts.

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

    Returns:
        dict: The created job.
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

    return api_client.jobs.create(config)


def get_or_create_job(
    api_client: APIClient,
    workflow: Workflow,
    materials: List[dict],
    project_id: str,
    owner_id: str,
    compute: Optional[dict] = None,
    prefix: Optional[str] = None,
    statuses: Iterable[str] = ("finished",),
) -> dict:
    """
    Returns an existing job for this material and workflow name if one with an allowed status
    exists under the given owner, otherwise creates a new one.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        workflow (Workflow): mat3ra-wode Workflow object (must have a .name and a .to_dict()).
        materials (list[dict]): Serialised material dicts; the first is the job's `_material`.
        project_id (str): Project ID.
        owner_id (str): Account ID under which to search and create.
        compute (dict, optional): Compute configuration dict.
        prefix (str, optional): Job name prefix for a newly created job; defaults to the
            workflow's own name, which already carries the per-material label.
        statuses (Iterable[str]): Job statuses that count as an existing job to reuse.

    Returns:
        dict: The job dict (existing or newly created), always carrying `status`.
    """
    query = {
        "_material._id": materials[0]["_id"],
        "owner._id": owner_id,
        "workflow.name": workflow.name,
        "status": {"$in": list(statuses)},
    }
    existing = api_client.jobs.list(query, {"sort": {"updatedAt": -1}, "limit": 1})
    if existing:
        print(f"♻️  Reusing already existing Job: {existing[0]['_id']} ({existing[0]['name']})")
        return existing[0]
    created = create_job(
        api_client=api_client,
        materials=materials,
        workflow=workflow.to_dict(),
        project_id=project_id,
        owner_id=owner_id,
        prefix=prefix or workflow.name,
        compute=compute,
    )
    job = api_client.jobs.get(created["_id"])
    print(f"✅ Job created: {job['_id']} ({job['name']})")
    return job


def submit_jobs(endpoint: JobEndpoints, job_ids: List[str]) -> None:
    """
    Submits jobs by IDs.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client.
        job_ids (list[str]): Job IDs to submit.
    """
    for job_id in job_ids:
        endpoint.submit(job_id)
