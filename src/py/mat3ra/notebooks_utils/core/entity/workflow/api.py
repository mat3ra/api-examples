from mat3ra.api_client import APIClient
from mat3ra.api_client.tools.workflow import (
    CUSTOM_SCRIPT_RUNNER,
    CUSTOM_SCRIPT_RUNNER_SH,
    copy_bank_workflow_by_system_name,
    set_execution_unit_input,
)
from mat3ra.wode import Workflow


def get_or_create_workflow(api_client: APIClient, workflow: Workflow, owner_id: str) -> dict:
    """
    Creates a workflow in the collection if none with the same hash exists under the given owner.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        workflow: mat3ra-wode Workflow object.
        owner_id (str): Account ID under which to search and create.

    Returns:
        dict: The workflow dict (existing or newly created).
    """
    existing = api_client.workflows.list({"hash": workflow.hash, "owner._id": owner_id})
    if existing:
        print(f"♻️  Reusing already existing Workflow: {existing[0]['_id']}")
        return existing[0]
    created = api_client.workflows.create(workflow.to_dict_without_special_keys(), owner_id=owner_id)
    print(f"✅ Workflow created: {created['_id']}")
    return created


__all__ = [
    "CUSTOM_SCRIPT_RUNNER",
    "CUSTOM_SCRIPT_RUNNER_SH",
    "copy_bank_workflow_by_system_name",
    "get_or_create_workflow",
    "set_execution_unit_input",
]
