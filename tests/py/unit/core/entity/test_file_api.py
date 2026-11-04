from typing import Any, Dict

from mat3ra.notebooks_utils.core.entity.file.api import to_object_storage_input

CLOUD_FILE: Dict[str, Any] = {
    "key": "my-account/user_script.py",
    "size": 14,
    "bucket": "test-bucket",
    "region": "us-west-2",
    "provider": "aws",
    "name": "user_script.py",
}


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
