import json
from typing import Dict, List

from mat3ra.api_client import APIClient
from mat3ra.api_client.endpoints import BaseEndpoint

# All of these land in the job's working directory after the IO unit has fetched the uploaded
# files, so an upload under any of them is overwritten before the user's script runs: the execution
# unit renders `script.py` and `requirements.txt`, and the runner it renders writes `material.json`.
# Keep in step with CUSTOM_SCRIPT_RUNNER in ../workflow/api.py.
RESERVED_FILENAMES = ("script.py", "requirements.txt", "material.json")


def _files_endpoint(api_client: APIClient) -> BaseEndpoint:
    """
    A raw endpoint for `/files`, which mat3ra-api-client does not model yet.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.

    Returns:
        BaseEndpoint: Endpoint bound to the same host, version and credentials as the client.
    """
    return BaseEndpoint(
        api_client.host,
        api_client.port,
        version=api_client.version,
        secure=api_client.secure,
        auth=api_client.auth,
    )


def upload_files(api_client: APIClient, files: Dict[str, str], account_id: str) -> List[dict]:
    """
    Uploads text files to the account's object storage ("Dropbox") folder.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        files (dict): File name (relative to the account folder) mapped to its text content.
        account_id (str): Account to upload under.

    Returns:
        list[dict]: One cloud file record per upload, with `key`, `size`, `bucket`, `region`
            and `provider`.

    Raises:
        ValueError: If a file name collides with one the execution unit writes itself.
    """
    reserved = [name for name in files if name.split("/")[-1] in RESERVED_FILENAMES]
    if reserved:
        raise ValueError(f"Rename {reserved}: {RESERVED_FILENAMES} are written by the workflow itself.")

    endpoint = _files_endpoint(api_client)
    headers = endpoint.get_headers(api_client.auth.account_id or "", api_client.auth.auth_token or "")

    uploaded = []
    for name, content in files.items():
        payload = {"name": name, "body": content, "accountId": account_id}
        record = endpoint.request("POST", "files", data=json.dumps(payload), headers=headers)
        print(f"⬆️  Uploaded {record['key']} ({record['size']} bytes)")
        uploaded.append(record)
    return uploaded


def to_object_storage_input(cloud_file: dict) -> dict:
    """
    Converts an upload record into an `object_storage` input item for a workflow IO unit.

    Args:
        cloud_file (dict): A record returned by `upload_files`.

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
