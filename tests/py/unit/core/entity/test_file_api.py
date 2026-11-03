import json
from typing import Any, Dict
from unittest.mock import MagicMock

from mat3ra.notebooks_utils.core.entity.file.api import (
    to_object_storage_input,
    upload_files,
)

CLOUD_FILE: Dict[str, Any] = {
    "key": "my-account/user_script.py",
    "size": 14,
    "bucket": "test-bucket",
    "region": "us-west-2",
    "provider": "aws",
    "lastModified": 1609891535,
    "name": "user_script.py",
}


SIGNED_UPLOAD = {
    "signedUrl": "https://s3/put?sig",
    "headers": {"Content-Type": "application/json"},
    "bucket": "b",
    "region": "r",
    "provider": "aws",
}


def _signed_upload_endpoint(monkeypatch, calls: list, puts: list) -> None:
    """A files endpoint that signs one upload per requested file; PUTs are recorded, not sent."""
    from mat3ra.notebooks_utils.core.entity.file import api as file_api

    def request(method, path, data=None, headers=None):
        payload = json.loads(data)
        calls.append((method, path, payload))
        return [{**SIGNED_UPLOAD, "key": f"user-abc/{file['name']}"} for file in payload["files"]]

    endpoint = MagicMock()
    endpoint.get_headers.return_value = {}
    endpoint.request.side_effect = request
    monkeypatch.setattr(file_api, "_files_endpoint", lambda client: endpoint)
    monkeypatch.setattr(file_api, "_put", lambda url, data, headers: puts.append((url, data, headers)))


def _client():
    client = MagicMock()
    client.auth.account_id = "acc"
    client.auth.auth_token = "tok"
    return client


def test_every_file_goes_through_one_signed_put_request(monkeypatch):
    """Text and bytes alike: one putObject request with size and type, then a PUT per file."""
    calls: list = []
    puts: list = []
    _signed_upload_endpoint(monkeypatch, calls, puts)

    upload_files(_client(), {"radii.json": '{"Si": 1.1}', "model.bin": b"\x00\x01binary"}, "acc")

    assert calls == [
        (
            "POST",
            "files/signed-urls",
            {
                "files": [
                    {"name": "radii.json", "size": 11, "contentType": "application/json"},
                    {"name": "model.bin", "size": 8, "contentType": "application/octet-stream"},
                ],
                "operation": "putObject",
                "accountId": "acc",
            },
        )
    ]
    assert puts == [
        ("https://s3/put?sig", b'{"Si": 1.1}', SIGNED_UPLOAD["headers"]),
        ("https://s3/put?sig", b"\x00\x01binary", SIGNED_UPLOAD["headers"]),
    ]


def test_text_is_uploaded_as_utf8_bytes(monkeypatch):
    calls: list = []
    puts: list = []
    _signed_upload_endpoint(monkeypatch, calls, puts)

    upload_files(_client(), {"notes.txt": "Å"}, "acc")

    assert calls[0][2]["files"] == [{"name": "notes.txt", "size": 2, "contentType": "text/plain"}]
    assert puts[0][1] == "Å".encode()


def test_upload_returns_records_the_runner_can_fetch(monkeypatch):
    _signed_upload_endpoint(monkeypatch, [], [])

    [record] = upload_files(_client(), {"model.bin": b"\x00\x01binary"}, "acc")

    assert record == {
        "name": "model.bin",
        "key": "user-abc/model.bin",
        "size": 8,
        "bucket": "b",
        "region": "r",
        "provider": "aws",
    }
    assert to_object_storage_input(record)["objectData"]["NAME"] == "user-abc/model.bin"


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
