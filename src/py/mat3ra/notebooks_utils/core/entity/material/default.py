"""
Default-material lookup.

Kept apart from api.py on purpose: notebooks that install only the `api` package group cannot import
mat3ra.made (which api.py needs), so this module may depend on mat3ra.api_client alone.
"""

from mat3ra.api_client import APIClient


def get_default_material(api_client: APIClient, owner_id: str) -> dict:
    """
    Returns the given account's default material.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID whose default material should be returned.

    Returns:
        dict: The account's default material document.
    """
    return api_client.materials.show_default(owner_id)
