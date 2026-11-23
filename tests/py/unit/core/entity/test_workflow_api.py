from unittest.mock import MagicMock

from mat3ra.notebooks_utils.core.entity.workflow.api import get_or_create_workflow
from mat3ra.standata.workflows import WorkflowStandata
from mat3ra.wode import Workflow

SAVED_WORKFLOW = {**WorkflowStandata.get_by_name_first_match("total_energy"), "_id": "workflow-1"}


def test_get_or_create_workflow_returns_the_saved_workflow_dict():
    client = MagicMock()
    client.workflows.list.return_value = [SAVED_WORKFLOW]

    workflow = get_or_create_workflow(client, Workflow.create(SAVED_WORKFLOW), "account-1")

    assert workflow["_id"] == SAVED_WORKFLOW["_id"]
