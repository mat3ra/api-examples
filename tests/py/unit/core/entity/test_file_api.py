import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.file.api import RESERVED_FILENAMES, to_object_storage_input, upload_files

ACCOUNT_ID = "account-1"

CLOUD_FILE: Dict[str, Any] = {
    "key": "my-account/user_script.py",
    "size": 14,
    "bucket": "test-bucket",
    "region": "us-west-2",
    "provider": "aws",
    "lastModified": 1609891535,
    "name": "user_script.py",
}


def _client(*records):
    """An APIClient whose files endpoint returns the given records, one per request."""
    client = MagicMock()
    client.host, client.port, client.version, client.secure = "localhost", 3000, "2018-10-01", False
    client.auth.account_id, client.auth.auth_token = ACCOUNT_ID, "token"
    client.auth.access_token = None
    return client


def test_upload_posts_name_and_body_per_file(monkeypatch):
    requests = []

    def request(method, path, data=None, headers=None):
        requests.append((method, path, json.loads(data)))
        return CLOUD_FILE

    endpoint = MagicMock()
    endpoint.request.side_effect = request
    endpoint.get_headers.return_value = {}
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.file.api._files_endpoint", lambda _: endpoint)

    uploaded = upload_files(_client(), {"user_script.py": "print(1)", "radii.json": "{}"}, ACCOUNT_ID)

    assert [r[:2] for r in requests] == [("POST", "files"), ("POST", "files")]
    assert [r[2] for r in requests] == [
        {"name": "user_script.py", "body": "print(1)", "accountId": ACCOUNT_ID},
        {"name": "radii.json", "body": "{}", "accountId": ACCOUNT_ID},
    ]
    assert uploaded == [CLOUD_FILE, CLOUD_FILE]


@pytest.mark.parametrize("name", RESERVED_FILENAMES)
def test_upload_refuses_a_name_the_job_would_overwrite(name, monkeypatch):
    endpoint = MagicMock()
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.file.api._files_endpoint", lambda _: endpoint)

    with pytest.raises(ValueError, match=name):
        upload_files(_client(), {name: "x"}, ACCOUNT_ID)

    endpoint.request.assert_not_called()


def test_object_storage_input_carries_every_field_the_runner_needs():
    """rupy requires all of NAME/PROVIDER/CONTAINER/REGION plus a basename, with no defaults."""
    assert to_object_storage_input(CLOUD_FILE) == {
        "type": "object_storage",
        "basename": "user_script.py",
        "pathname": "",
        "objectData": {
            "NAME": "my-account/user_script.py",
            "PROVIDER": "aws",
            "CONTAINER": "test-bucket",
            "REGION": "us-west-2",
        },
    }


def test_object_storage_basename_is_the_name_the_script_opens():
    nested = {**CLOUD_FILE, "key": "my-account/assets/radii.json"}

    assert to_object_storage_input(nested)["basename"] == "radii.json"


def test_upload_refuses_the_shell_runner_name():
    """hello_world.sh is what the shell workflow's runner lands as - an upload would be clobbered."""
    with pytest.raises(ValueError, match="hello_world.sh"):
        upload_files(None, {"hello_world.sh": "echo hi"}, "account")


def test_object_storage_pathname_targets_a_subdirectory():
    """A pathname of "pseudo" fetches the file into <work_dir>/pseudo — where QE's pseudo_dir points."""
    item = to_object_storage_input(CLOUD_FILE, pathname="pseudo")

    assert item["pathname"] == "pseudo"
    assert item["basename"] == "user_script.py"
