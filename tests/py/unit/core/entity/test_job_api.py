from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.job.api import create_job, find_job_for_material

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
EXISTING_JOB: Dict[str, Any] = {"_id": "job-0", "name": "Fixed-cell Relaxation V_B pbe-us", "status": "finished"}
RELAX_WORKFLOW_NAME = "Fixed-cell Relaxation V_B pbe-us"


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
    [("finished",), ("submitted", "queued", "active")],
)
def test_find_job_for_material_returns_the_job_when_found(statuses):
    client = MagicMock()
    client.jobs.list.return_value = [EXISTING_JOB]

    job = find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID, statuses=statuses)

    assert job == EXISTING_JOB
    client.jobs.list.assert_called_once_with(
        {
            "_material._id": MATERIAL_INITIAL["_id"],
            "owner._id": OWNER_ID,
            "workflow.name": RELAX_WORKFLOW_NAME,
            "status": {"$in": list(statuses)},
        },
        {"sort": {"updatedAt": -1}, "limit": 1},
    )


def test_find_job_for_material_returns_none_when_not_found():
    client = MagicMock()
    client.jobs.list.return_value = []

    job = find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID)

    assert job is None


def test_find_job_for_material_defaults_to_finished_only():
    client = MagicMock()
    client.jobs.list.return_value = []

    find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID)

    assert client.jobs.list.call_args.args[0]["status"] == {"$in": ["finished"]}
