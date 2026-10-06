import ast
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.material import default as material_default
from mat3ra.notebooks_utils.core.entity.material.default import get_default_material
from mat3ra.notebooks_utils.core.entity.project import api as project_api
from mat3ra.notebooks_utils.core.entity.project.api import get_default_project
from mat3ra.notebooks_utils.core.entity.workflow import default as workflow_default
from mat3ra.notebooks_utils.core.entity.workflow.default import get_default_workflow

ACCOUNT_ID = "account-1"
DEFAULT_ENTITY = {"_id": "default-1", "isDefault": True}
# The `api` package group of config.yml installs only these, so the default lookups may import nothing else.
ALLOWED_IMPORTED_MODULES = {"mat3ra.api_client"}


@pytest.mark.parametrize(
    ("get_default", "endpoint_name"),
    [
        (get_default_material, "materials"),
        (get_default_workflow, "workflows"),
        (get_default_project, "projects"),
    ],
)
def test_returns_the_default_entity_of_the_given_account(get_default, endpoint_name):
    client = MagicMock()
    getattr(client, endpoint_name).show_default.return_value = DEFAULT_ENTITY

    assert get_default(client, ACCOUNT_ID) == DEFAULT_ENTITY
    getattr(client, endpoint_name).show_default.assert_called_once_with(ACCOUNT_ID)


@pytest.mark.parametrize("module", [material_default, workflow_default, project_api])
def test_default_lookups_import_only_the_api_client(module):
    """Notebooks installing just the `api` package group must be able to import these."""
    with open(module.__file__) as module_file:
        tree = ast.parse(module_file.read())

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module)

    assert imported_modules <= ALLOWED_IMPORTED_MODULES
