"""
Default-workflow lookup.

Kept apart from api.py on purpose: notebooks that install only the `api` package group cannot import
mat3ra.wode (which api.py needs), so this module may depend on mat3ra.api_client alone.
"""

from mat3ra.api_client import APIClient


def get_default_workflow(api_client: APIClient, owner_id: str) -> dict:
    """
    Returns the given account's default workflow.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID whose default workflow should be returned.

    Returns:
        dict: The account's default workflow document.
    """
    return api_client.workflows.show_default(owner_id)
