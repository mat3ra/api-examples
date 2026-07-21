import urllib.request
from typing import Any, Dict, List, Optional, Union

from mat3ra.api_client import APIClient, JobEndpoints


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
    return {
        "_id": materials_set["_id"],
        "cls": "Material",
        "slug": materials_set.get("slug") or materials_set.get("name") or "",
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

    return api_client.jobs.create(config)


def submit_jobs(endpoint: JobEndpoints, job_ids: List[str]) -> None:
    """
    Submits jobs by IDs.

    Args:
        endpoint (JobEndpoints): Job endpoint object from the Exabyte API Client.
        job_ids (list[str]): Job IDs to submit.
    """
    for job_id in job_ids:
        endpoint.submit(job_id)
