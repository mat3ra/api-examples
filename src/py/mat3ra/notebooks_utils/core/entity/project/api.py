from mat3ra.api_client import APIClient


def get_default_project(api_client: APIClient, owner_id: str) -> dict:
    """
    Returns the given account's default project.

    Uses .request() with flat params instead of .list(): .list() always wraps its argument as
    a query=<json> blob, which the projects list endpoint (migrated to a validated use case)
    silently drops since it only accepts flat, declared keys - unfiltered, it returns every
    project visible to the session, so the first result is not necessarily this account's own.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID whose default project should be returned.

    Returns:
        dict: The account's default project document.

    Raises:
        ValueError: If the account has no default project.
    """
    projects = api_client.projects.request(
        "GET", api_client.projects.name, params={"isDefault": "true", "ownerId": owner_id},
        headers=api_client.projects.headers,
    )
    if not projects:
        raise ValueError(f"Account {owner_id} has no default project.")
    return projects[0]
