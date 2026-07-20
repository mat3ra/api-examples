from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.material.api import find_material_set, list_materials_by_set

OWNER_ID = "account-1"
SET_NAME = "H2+H"
SET_ID = "set-1"

MATERIAL_INITIAL: Dict[str, Any] = {
    "_id": "m-initial",
    "name": "path-start",
    "isEntitySet": False,
    "inSet": [{"_id": SET_ID, "index": 0}],
}
MATERIAL_IMAGE: Dict[str, Any] = {
    "_id": "m-image",
    "name": "path-mid",
    "isEntitySet": False,
    "inSet": [{"_id": SET_ID, "index": 1}],
}
MATERIAL_FINAL: Dict[str, Any] = {
    "_id": "m-final",
    "name": "path-end",
    "isEntitySet": False,
    "inSet": [{"_id": SET_ID, "index": 2}],
}
ENTITY_SET: Dict[str, Any] = {"_id": SET_ID, "name": "H2+H", "isEntitySet": True}

# Scrambled API order — list_materials_by_set must sort by inSet.index
SET_MEMBER_MATERIALS: List[Dict[str, Any]] = [
    MATERIAL_FINAL,
    MATERIAL_INITIAL,
    MATERIAL_IMAGE,
    ENTITY_SET,
]


def _client_with_list_responses(responses: List[List[Dict[str, Any]]]) -> MagicMock:
    client = MagicMock()
    client.materials.list.side_effect = responses
    return client


def test_find_material_set_returns_first_match():
    client = _client_with_list_responses([[ENTITY_SET]])
    material_set = find_material_set(client, OWNER_ID, SET_NAME)
    assert material_set["_id"] == SET_ID
    client.materials.list.assert_called_once_with(
        {
            "owner._id": OWNER_ID,
            "isEntitySet": True,
            "name": {"$regex": SET_NAME, "$options": "i"},
        }
    )


def test_find_material_set_raises_when_missing():
    client = _client_with_list_responses([[]])
    with pytest.raises(ValueError, match="No material set matching"):
        find_material_set(client, OWNER_ID, SET_NAME)


@pytest.mark.parametrize(
    ("members", "expected_ids"),
    [
        (SET_MEMBER_MATERIALS, ["m-initial", "m-image", "m-final"]),
        ([MATERIAL_INITIAL], ["m-initial"]),
    ],
)
def test_list_materials_by_set_orders_by_inset_index(members, expected_ids):
    client = _client_with_list_responses([[ENTITY_SET], members])
    materials = list_materials_by_set(client, OWNER_ID, SET_NAME)
    assert [material["_id"] for material in materials] == expected_ids
    assert client.materials.list.call_args_list[1].args[0] == {
        "owner._id": OWNER_ID,
        "inSet._id": SET_ID,
    }
