from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.job.api import create_job, get_or_create_job

OWNER_ID = "account-1"
PROJECT_ID = "project-1"
JOB_PREFIX = "NEB H2+H"
MATERIAL_SET_ID = "set-1"
MATERIAL_SET_NAME = "H2+H"

MATERIAL_INITIAL: Dict[str, Any] = {"_id": "m-initial", "name": "initial"}
MATERIAL_FINAL: Dict[str, Any] = {"_id": "m-final", "name": "final"}
MATERIALS: List[Dict[str, Any]] = [MATERIAL_INITIAL, MATERIAL_FINAL]

MULTI_MATERIAL_WORKFLOW: Dict[str, Any] = {
    "_id": "workflow-1",
    "name": "NEB",
    "isMultiMaterial": True,
}
SINGLE_MATERIAL_WORKFLOW: Dict[str, Any] = {
    "_id": "workflow-2",
    "name": "Total Energy",
    "isMultiMaterial": False,
}
MATERIALS_SET: Dict[str, Any] = {
    "_id": MATERIAL_SET_ID,
    "name": MATERIAL_SET_NAME,
    "slug": MATERIAL_SET_NAME,
    "isEntitySet": True,
}
CREATED_JOB: Dict[str, Any] = {"_id": "job-1", "name": JOB_PREFIX}
CREATED_JOB_FULL: Dict[str, Any] = {"_id": "job-1", "name": JOB_PREFIX, "status": "pre-submission"}
EXISTING_JOB: Dict[str, Any] = {"_id": "job-0", "name": "Fixed-cell Relaxation V_B pbe-us", "status": "finished"}

RELAX_WORKFLOW = SimpleNamespace(
    name="Fixed-cell Relaxation V_B pbe-us",
    to_dict=lambda: {"name": "Fixed-cell Relaxation V_B pbe-us", "isMultiMaterial": False},
)


@pytest.mark.parametrize(
    ("workflow", "materials_set", "expected_materials_set"),
    [
        (MULTI_MATERIAL_WORKFLOW, MATERIALS_SET, True),
        (MULTI_MATERIAL_WORKFLOW, None, False),
        (SINGLE_MATERIAL_WORKFLOW, MATERIALS_SET, True),
    ],
)
def test_create_job_sets_materials_set_when_provided(workflow, materials_set, expected_materials_set):
    client = MagicMock()
    client.jobs.create.return_value = CREATED_JOB
    workflow_payload = dict(workflow)

    job = create_job(
        api_client=client,
        materials=MATERIALS,
        workflow=workflow_payload,
        project_id=PROJECT_ID,
        owner_id=OWNER_ID,
        prefix=JOB_PREFIX,
        materials_set=materials_set,
    )

    assert job["_id"] == "job-1"
    config = client.jobs.create.call_args.args[0]
    assert "_id" not in workflow_payload
    assert ("_materialsSet" in config) is expected_materials_set
    if expected_materials_set:
        assert config["_materialsSet"] == {
            "_id": MATERIAL_SET_ID,
            "cls": "Material",
            "slug": MATERIAL_SET_NAME,
        }
    if workflow.get("isMultiMaterial"):
        assert config["_materials"] == [{"_id": "m-initial"}, {"_id": "m-final"}]
    else:
        assert "_materials" not in config


@pytest.mark.parametrize(
    "statuses",
    [("finished",), ("submitted", "queued", "active", "finished")],
)
def test_get_or_create_job_reuses_when_found(statuses):
    client = MagicMock()
    client.jobs.list.return_value = [EXISTING_JOB]

    job = get_or_create_job(client, RELAX_WORKFLOW, MATERIALS, PROJECT_ID, OWNER_ID, statuses=statuses)

    assert job["_id"] == EXISTING_JOB["_id"]
    client.jobs.list.assert_called_once_with(
        {
            "_material._id": MATERIAL_INITIAL["_id"],
            "owner._id": OWNER_ID,
            "workflow.name": RELAX_WORKFLOW.name,
            "status": {"$in": list(statuses)},
        },
        {"sort": {"updatedAt": -1}, "limit": 1},
    )
    client.jobs.create.assert_not_called()


def test_get_or_create_job_creates_when_not_found():
    client = MagicMock()
    client.jobs.list.return_value = []
    client.jobs.create.return_value = CREATED_JOB
    client.jobs.get.return_value = CREATED_JOB_FULL

    job = get_or_create_job(client, RELAX_WORKFLOW, MATERIALS, PROJECT_ID, OWNER_ID, prefix=JOB_PREFIX)

    assert job == CREATED_JOB_FULL
    client.jobs.get.assert_called_once_with(CREATED_JOB["_id"])
    config = client.jobs.create.call_args.args[0]
    assert config["workflow"]["name"] == RELAX_WORKFLOW.name
    assert config["name"] == JOB_PREFIX


def test_get_or_create_job_defaults_to_finished_only():
    client = MagicMock()
    client.jobs.list.return_value = []
    client.jobs.create.return_value = CREATED_JOB
    client.jobs.get.return_value = CREATED_JOB_FULL

    get_or_create_job(client, RELAX_WORKFLOW, MATERIALS, PROJECT_ID, OWNER_ID)

    assert client.jobs.list.call_args.args[0]["status"] == {"$in": ["finished"]}


def test_get_or_create_job_defaults_prefix_to_workflow_name():
    client = MagicMock()
    client.jobs.list.return_value = []
    client.jobs.create.return_value = CREATED_JOB
    client.jobs.get.return_value = CREATED_JOB_FULL

    get_or_create_job(client, RELAX_WORKFLOW, MATERIALS, PROJECT_ID, OWNER_ID)

    assert client.jobs.create.call_args.args[0]["name"] == RELAX_WORKFLOW.name
