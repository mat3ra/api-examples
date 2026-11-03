def to_object_storage_input(cloud_file: dict) -> dict:
    """
    Converts an upload record into an `object_storage` input item for a workflow IO unit.

    Args:
        cloud_file (dict): A record returned by `client.files.upload` (mat3ra-api-client).

    Returns:
        dict: IO unit input item. The runner fetches it into the job's working directory under
            `basename`, which is what makes the user script's relative paths resolve.
    """
    return {
        "type": "object_storage",
        "basename": cloud_file["key"].split("/")[-1],
        "pathname": "",
        "objectData": {
            "NAME": cloud_file["key"],
            "PROVIDER": cloud_file["provider"],
            "CONTAINER": cloud_file["bucket"],
            "REGION": cloud_file["region"],
        },
    }
