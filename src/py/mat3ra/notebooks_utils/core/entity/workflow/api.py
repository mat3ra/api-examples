from mat3ra.api_client import APIClient
from mat3ra.api_client.tools.workflow import (
    CUSTOM_SCRIPT_RUNNER,
    CUSTOM_SCRIPT_RUNNER_SH,
    copy_bank_workflow_by_system_name,
)
from mat3ra.api_client.tools.workflow import get_or_create_workflow as _get_or_create_workflow
from mat3ra.api_client.tools.workflow import set_execution_unit_input
from mat3ra.wode import Workflow


def get_or_create_workflow(api_client: APIClient, workflow: Workflow, owner_id: str) -> dict:
    """
    `get_or_create_workflow` of mat3ra.api_client.tools, returning the saved workflow as the dict the notebooks read.
    """
    return _get_or_create_workflow(api_client, workflow, owner_id).to_dict()


__all__ = [
    "CUSTOM_SCRIPT_RUNNER",
    "CUSTOM_SCRIPT_RUNNER_SH",
    "copy_bank_workflow_by_system_name",
    "get_or_create_workflow",
    "set_execution_unit_input",
]
