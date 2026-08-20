from mat3ra.api_client import APIClient, BankWorkflowEndpoints
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


def copy_bank_workflow_by_system_name(endpoint: BankWorkflowEndpoints, system_name: str, account_id: str) -> dict:
    """
    Copies a bank workflow with given system name into the account's workflows.

    Args:
        endpoint (BankWorkflowEndpoints): an instance of BankWorkflowEndpoints class
        system_name (str): workflow system name.
        account_id (str): ID of account to copy the bank workflow into.

    Returns:
        dict: new account's workflow
    """
    bank_workflow_id = endpoint.list({"systemName": system_name})[0]["_id"]
    return endpoint.copy(bank_workflow_id, account_id)["_id"]


# Written by the runner into the job's working directory, next to the files the IO unit fetched.
# The filenames it writes are also listed in RESERVED_FILENAMES in ../file/api.py, which refuses an
# upload that would be overwritten by them; change both together.
CUSTOM_SCRIPT_RUNNER = '''import json

with open("material.json", "w") as file:
    json.dump(json.loads(r"""{{ MATERIAL | default({}) | tojson }}"""), file)

with open("settings.json", "w") as file:
    json.dump(json.loads(r"""{{ SETTINGS | default({}) | tojson }}"""), file)

with open("user_script.py") as file:
    exec(compile(file.read(), "user_script.py", "exec"))
'''


def set_execution_unit_input(unit: dict, template_name: str, content: str) -> None:
    """
    Replaces one input file of an execution unit with fixed content.

    `isManuallyChanged` stops the platform re-rendering the file at job creation, which is what
    lets the runner keep its `{{ ... }}` placeholders for the compute node to resolve, and keeps a
    user's requirements verbatim. Inputs are matched by template name rather than position, so
    adding a file to the flavor cannot silently write content into the wrong one.

    Args:
        unit (dict): Execution unit config from a workflow.
        template_name (str): Name of the input file to replace, e.g. "script.py".
        content (str): Content to write.

    Raises:
        KeyError: If the unit has no input with that template name.
    """
    for unit_input in unit["input"]:
        if unit_input["template"]["name"] == template_name:
            unit_input["template"]["content"] = content
            unit_input["rendered"] = content
            unit_input["isManuallyChanged"] = True
            return
    available = [unit_input["template"]["name"] for unit_input in unit["input"]]
    raise KeyError(f"No input named '{template_name}' in unit '{unit.get('name')}'. Available: {available}")
