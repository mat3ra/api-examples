import json
import mimetypes
from typing import Dict, List, Union

from mat3ra.api_client import APIClient
from mat3ra.api_client.endpoints import BaseEndpoint
from mat3ra.notebooks_utils.primitive.environment import is_pyodide_environment

if is_pyodide_environment():
    from js import XMLHttpRequest  # type: ignore[import-not-found]
    from pyodide.ffi import to_js  # type: ignore[import-not-found]
else:
    from urllib.request import Request, urlopen


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


def upload_files(api_client: APIClient, files: Dict[str, Union[str, bytes]], account_id: str) -> List[dict]:
    """
    Uploads files to the account's object storage ("Dropbox") folder.

    The platform signs one PUT URL per file (`POST /files/signed-urls`, `putObject`) for the declared
    size and content type, and the content is PUT to storage directly, so no request body limit
    applies. Text is uploaded as UTF-8.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        files (dict): File name (relative to the account folder) mapped to its content, `str` for
            text or `bytes` for anything else.
        account_id (str): Account to upload under.

    Returns:
        list[dict]: One cloud file record per upload, with `name`, `key`, `size`, `bucket`,
            `region` and `provider`.
    """
    contents = {
        name: content.encode("utf-8") if isinstance(content, str) else content for name, content in files.items()
    }
    targets = _request_upload_urls(api_client, contents, account_id)

    uploaded = []
    for (name, content), target in zip(contents.items(), targets):
        _put(target["signedUrl"], content, target["headers"])
        record = _to_cloud_file(name, content, target)
        print(f"⬆️  Uploaded {record['key']} ({record['size']} bytes)")
        uploaded.append(record)
    return uploaded


def _request_upload_urls(api_client: APIClient, contents: Dict[str, bytes], account_id: str) -> List[dict]:
    """Asks the platform for one signed PUT URL per file, in the order given."""
    endpoint = _files_endpoint(api_client)
    headers = endpoint.get_headers(api_client.auth.account_id or "", api_client.auth.auth_token or "")
    payload = {
        "files": [
            {"name": name, "size": len(content), "contentType": _content_type(name)}
            for name, content in contents.items()
        ],
        "operation": "putObject",
        "accountId": account_id,
    }
    return endpoint.request("POST", "files/signed-urls", data=json.dumps(payload), headers=headers)


def _content_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _to_cloud_file(name: str, content: bytes, target: dict) -> dict:
    return {
        "name": name,
        "key": target["key"],
        "size": len(content),
        "bucket": target["bucket"],
        "region": target["region"],
        "provider": target["provider"],
    }


def _put(url: str, data: bytes, headers: Dict[str, str]) -> None:
    """
    PUTs bytes to a signed URL - from the browser in JupyterLite, from the process elsewhere. The
    headers are part of the signature, so they are sent exactly as the platform returned them.
    """
    if not is_pyodide_environment():
        with urlopen(Request(url, data=data, headers=headers, method="PUT")) as response:
            response.read()
        return

    request = XMLHttpRequest.new()
    request.open("PUT", url, False)
    for header, value in headers.items():
        request.setRequestHeader(header, value)
    request.send(to_js(data))
    if request.status < 200 or request.status >= 300:
        raise RuntimeError(f"PUT to storage failed with HTTP {request.status}: {request.responseText}")


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
