from mat3ra.api_client import APIClient


def get_default_project(api_client: APIClient, owner_id: str) -> dict:
    """
    Returns the given account's default project.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID whose default project should be returned.

    Returns:
        dict: The account's default project document.
    """
    return api_client.projects.show_default(owner_id)
