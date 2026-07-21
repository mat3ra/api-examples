from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.material.api import (
    find_material_set,
    get_or_create_materials_set,
    list_materials_by_set,
)

OWNER_ID = "account-1"
MATERIAL_SET_NAME = "H2+H"
MATERIAL_SET_ID = "set-1"

MATERIAL_INITIAL: Dict[str, Any] = {
    "_id": "m-initial",
    "name": "path-start",
    "isEntitySet": False,
    "inSet": [{"_id": MATERIAL_SET_ID, "index": 0}],
}
MATERIAL_IMAGE: Dict[str, Any] = {
    "_id": "m-image",
    "name": "path-mid",
    "isEntitySet": False,
    "inSet": [{"_id": MATERIAL_SET_ID, "index": 1}],
}
MATERIAL_FINAL: Dict[str, Any] = {
    "_id": "m-final",
    "name": "path-end",
    "isEntitySet": False,
    "inSet": [{"_id": MATERIAL_SET_ID, "index": 2}],
}
ENTITY_SET: Dict[str, Any] = {
    "_id": MATERIAL_SET_ID,
    "name": "H2+H",
    "isEntitySet": True,
    "entitySetType": "ordered",
}

SET_MEMBER_MATERIALS_OUT_OF_ORDER: List[Dict[str, Any]] = [
    MATERIAL_FINAL,
    MATERIAL_INITIAL,
    MATERIAL_IMAGE,
    ENTITY_SET,
]
EXPECTED_ORDERED_IDS = ["m-initial", "m-image", "m-final"]
EXPECTED_SINGLE_MEMBER_IDS = ["m-initial"]


def _client_with_list_responses(responses: List[List[Dict[str, Any]]]) -> MagicMock:
    client = MagicMock()
    client.materials.list.side_effect = responses
    return client


def test_find_material_set_returns_first_match():
    client = _client_with_list_responses([[ENTITY_SET]])

    material_set = find_material_set(client, OWNER_ID, MATERIAL_SET_NAME)

    assert material_set["_id"] == MATERIAL_SET_ID
    client.materials.list.assert_called_once_with(
        {
            "owner._id": OWNER_ID,
            "isEntitySet": True,
            "name": {"$regex": MATERIAL_SET_NAME, "$options": "i"},
        }
    )


def test_find_material_set_raises_when_missing():
    client = _client_with_list_responses([[]])

    with pytest.raises(ValueError, match="No material set matching"):
        find_material_set(client, OWNER_ID, MATERIAL_SET_NAME)


@pytest.mark.parametrize(
    ("members", "expected_ids"),
    [
        (SET_MEMBER_MATERIALS_OUT_OF_ORDER, EXPECTED_ORDERED_IDS),
        ([MATERIAL_INITIAL], EXPECTED_SINGLE_MEMBER_IDS),
    ],
)
def test_list_materials_by_set_orders_by_inset_index(members, expected_ids):
    client = _client_with_list_responses([[ENTITY_SET], members])

    materials = list_materials_by_set(client, OWNER_ID, MATERIAL_SET_NAME)

    assert [material["_id"] for material in materials] == expected_ids
    assert client.materials.list.call_args_list[1].args[0] == {
        "owner._id": OWNER_ID,
        "inSet._id": MATERIAL_SET_ID,
    }


@pytest.mark.parametrize(
    ("is_ordered", "expected_entity_set_type", "materials"),
    [
        (True, "ordered", [MATERIAL_INITIAL, MATERIAL_FINAL]),
        (False, "unordered", [MATERIAL_INITIAL]),
    ],
)
def test_get_or_create_materials_set_creates_when_missing(is_ordered, expected_entity_set_type, materials):
    client = _client_with_list_responses([[]])
    client.materials.create_set.return_value = {
        **ENTITY_SET,
        "entitySetType": expected_entity_set_type,
    }

    materials_set = get_or_create_materials_set(
        client,
        OWNER_ID,
        MATERIAL_SET_NAME,
        materials,
        is_ordered=is_ordered,
    )

    assert materials_set["_id"] == MATERIAL_SET_ID
    client.materials.create_set.assert_called_once_with(
        {
            "name": MATERIAL_SET_NAME,
            "owner": {"_id": OWNER_ID},
            "entitySetType": expected_entity_set_type,
        }
    )
    assert client.materials.move_to_set.call_args_list[0].args == (
        materials[0]["_id"],
        "",
        MATERIAL_SET_ID,
    )


def test_get_or_create_materials_set_reuses_when_found():
    client = _client_with_list_responses([[ENTITY_SET]])
    materials = [MATERIAL_INITIAL, MATERIAL_FINAL]

    materials_set = get_or_create_materials_set(
        client,
        OWNER_ID,
        MATERIAL_SET_NAME,
        materials,
        is_ordered=True,
    )

    assert materials_set["_id"] == MATERIAL_SET_ID
    client.materials.create_set.assert_not_called()
    assert client.materials.move_to_set.call_args_list[0].args == (
        materials[0]["_id"],
        "",
        MATERIAL_SET_ID,
    )


def test_get_or_create_materials_set_ordered_requires_two_materials():
    client = MagicMock()

    with pytest.raises(ValueError, match="at least two materials"):
        get_or_create_materials_set(
            client,
            OWNER_ID,
            MATERIAL_SET_NAME,
            [MATERIAL_INITIAL],
            is_ordered=True,
        )
    client.materials.list.assert_not_called()


def test_get_or_create_materials_set_requires_one_material():
    client = MagicMock()

    with pytest.raises(ValueError, match="at least one material"):
        get_or_create_materials_set(
            client,
            OWNER_ID,
            MATERIAL_SET_NAME,
            [],
            is_ordered=False,
        )
    client.materials.list.assert_not_called()
