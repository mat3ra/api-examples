from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.job.api import create_job

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
