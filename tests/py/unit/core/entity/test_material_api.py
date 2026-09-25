import json
import re
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.material.api import (
    find_material_set,
    find_relaxed_material,
    get_final_structure_for_job,
    get_or_create_materials_set,
    list_materials_by_set,
    list_materials_in_set,
    load_material,
)
from mat3ra.standata.materials import Materials

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
    client.materials.request.side_effect = responses
    return client


def test_find_material_set_returns_first_match():
    client = _client_with_list_responses([[ENTITY_SET]])

    material_set = find_material_set(client, OWNER_ID, MATERIAL_SET_NAME)

    assert material_set["_id"] == MATERIAL_SET_ID
    client.materials.request.assert_called_once_with(
        "GET",
        client.materials.name,
        params={"ownerId": OWNER_ID, "isEntitySet": "true"},
        headers=client.materials.headers,
    )
    assert "+" in MATERIAL_SET_NAME
    assert re.escape(MATERIAL_SET_NAME) != MATERIAL_SET_NAME


def test_find_material_set_raises_when_missing():
    client = _client_with_list_responses([[]])

    with pytest.raises(ValueError, match="No material set matching"):
        find_material_set(client, OWNER_ID, MATERIAL_SET_NAME)


def test_find_material_set_rejects_unordered_when_order_required():
    client = _client_with_list_responses([[{**ENTITY_SET, "entitySetType": "unordered"}]])

    with pytest.raises(ValueError, match="is 'unordered', not 'ordered'"):
        find_material_set(client, OWNER_ID, MATERIAL_SET_NAME, require_ordered=True)


def test_list_materials_by_set_rejects_unordered_when_order_required():
    client = _client_with_list_responses([[{**ENTITY_SET, "entitySetType": "unordered"}]])

    with pytest.raises(ValueError, match="is 'unordered', not 'ordered'"):
        list_materials_by_set(client, OWNER_ID, MATERIAL_SET_NAME, require_ordered=True)
    assert client.materials.request.call_count == 1


def test_list_materials_in_set_does_not_re_resolve_the_set():
    client = _client_with_list_responses([SET_MEMBER_MATERIALS_OUT_OF_ORDER])

    materials = list_materials_in_set(client, OWNER_ID, ENTITY_SET)

    assert [material["_id"] for material in materials] == EXPECTED_ORDERED_IDS
    client.materials.request.assert_called_once_with(
        "GET",
        client.materials.name,
        params={"ownerId": OWNER_ID, "setId": MATERIAL_SET_ID, "isEntitySet": "false"},
        headers=client.materials.headers,
    )


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
    assert client.materials.request.call_args_list[1].kwargs["params"] == {
        "ownerId": OWNER_ID,
        "setId": MATERIAL_SET_ID,
        "isEntitySet": "false",
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


def test_get_or_create_materials_set_rejects_reuse_with_mismatched_type():
    unordered_set = {**ENTITY_SET, "entitySetType": "unordered"}
    client = _client_with_list_responses([[unordered_set]])

    with pytest.raises(ValueError, match="already exists as 'unordered'"):
        get_or_create_materials_set(
            client,
            OWNER_ID,
            MATERIAL_SET_NAME,
            [MATERIAL_INITIAL, MATERIAL_FINAL],
            is_ordered=True,
        )
    client.materials.move_to_set.assert_not_called()


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
    client.materials.request.assert_not_called()


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
    client.materials.request.assert_not_called()


DEFECTIVE_HASH = "hash-defective"
RELAXED_HASH = "hash-relaxed"
DEFECTIVE_MATERIAL = SimpleNamespace(hash=DEFECTIVE_HASH)
SAVED_DEFECTIVE: Dict[str, Any] = {"_id": "m-defective", "name": "B-vacancy h-BN", "hash": DEFECTIVE_HASH}
FINISHED_JOB: Dict[str, Any] = {"_id": "job-1", "name": "Fixed-cell Relaxation", "status": "finished"}
RELAXED_MATERIAL_DOC: Dict[str, Any] = {
    **Materials.get_by_name_first_match("Silicon"),
    "name": "B-vacancy h-BN relaxed",
    "hash": RELAXED_HASH,
}
# Same hash as the input material: an SCF's own output, not a relaxation.
SCF_MATERIAL_DOC: Dict[str, Any] = {
    **Materials.get_by_name_first_match("Silicon"),
    "name": "B-vacancy h-BN",
    "hash": DEFECTIVE_HASH,
}


def test_find_relaxed_material_returns_final_structure_from_the_job():
    client = MagicMock()
    client.materials.request.return_value = [SAVED_DEFECTIVE]
    client.jobs.request.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-relaxed"}]
    client.materials.get.return_value = RELAXED_MATERIAL_DOC

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    client.materials.request.assert_called_once_with(
        "GET",
        client.materials.name,
        params={"hashes": DEFECTIVE_HASH, "ownerId": OWNER_ID},
        headers=client.materials.headers,
    )
    client.jobs.request.assert_called_once_with(
        "GET",
        client.jobs.name,
        params={"materialId": [SAVED_DEFECTIVE["_id"]], "ownerId": OWNER_ID, "status": "finished"},
        headers=client.jobs.headers,
    )
    client.properties.get_for_job.assert_called_once_with(FINISHED_JOB["_id"], "final_structure")
    client.materials.get.assert_called_once_with("m-relaxed")


def test_find_relaxed_material_uses_the_last_final_structure_entry():
    # A relaxation job's final_structure property can carry more than one entry: the initial
    # structure (same hash as the input) first, the relaxed one last -- PLAN #27.
    client = MagicMock()
    client.materials.request.return_value = [SAVED_DEFECTIVE]
    client.jobs.request.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-initial"}, {"materialId": "m-relaxed"}]
    client.materials.get.side_effect = lambda material_id: {
        "m-initial": SCF_MATERIAL_DOC,
        "m-relaxed": RELAXED_MATERIAL_DOC,
    }[material_id]

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    client.materials.get.assert_called_once_with("m-relaxed")


def test_find_relaxed_material_returns_none_when_material_is_not_on_the_platform():
    client = MagicMock()
    client.materials.request.return_value = []
    client.jobs.request.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    # No matching materials -> nothing to filter jobs by, so the jobs endpoint is never queried.
    client.jobs.request.assert_not_called()


def test_find_relaxed_material_returns_none_when_no_job_exists():
    client = MagicMock()
    client.materials.request.return_value = [SAVED_DEFECTIVE]
    client.jobs.request.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    client.properties.get_for_job.assert_not_called()


def test_find_relaxed_material_returns_none_when_job_has_no_final_structure():
    client = MagicMock()
    client.materials.request.return_value = [SAVED_DEFECTIVE]
    client.jobs.request.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    client.materials.get.assert_not_called()


def test_find_relaxed_material_checks_every_same_hash_material():
    other_material: Dict[str, Any] = {"_id": "m-other", "name": "B-vacancy h-BN", "hash": DEFECTIVE_HASH}
    client = MagicMock()
    client.materials.request.return_value = [other_material, SAVED_DEFECTIVE]
    client.jobs.request.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-relaxed"}]
    client.materials.get.return_value = RELAXED_MATERIAL_DOC

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    client.jobs.request.assert_called_once_with(
        "GET",
        client.jobs.name,
        params={
            "materialId": [other_material["_id"], SAVED_DEFECTIVE["_id"]],
            "ownerId": OWNER_ID,
            "status": "finished",
        },
        headers=client.jobs.headers,
    )


def test_find_relaxed_material_skips_a_final_structure_with_the_same_hash():
    scf_job: Dict[str, Any] = {"_id": "job-scf", "name": "Total Energy", "status": "finished"}
    relax_job: Dict[str, Any] = {"_id": "job-relax", "name": "Fixed-cell Relaxation", "status": "finished"}
    client = MagicMock()
    client.materials.request.return_value = [SAVED_DEFECTIVE]
    client.jobs.request.return_value = [scf_job, relax_job]
    client.properties.get_for_job.side_effect = [[{"materialId": "m-scf"}], [{"materialId": "m-relaxed"}]]
    client.materials.get.side_effect = [SCF_MATERIAL_DOC, RELAXED_MATERIAL_DOC]

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    assert client.properties.get_for_job.call_count == 2


SILICON_NAMED = {**Materials.get_by_name_first_match("Silicon"), "name": "Silicon"}


def test_load_material_finds_an_exact_match_in_the_folder(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(SILICON_NAMED))
    client = MagicMock()

    material = load_material(client, str(tmp_path), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.request.assert_not_called()


def test_load_material_falls_back_to_the_account(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(Materials.get_by_name_first_match("Silicon")))
    client = MagicMock()
    client.materials.request.return_value = [SILICON_NAMED]

    material = load_material(client, str(tmp_path), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.request.assert_called_once_with(
        "GET",
        client.materials.name,
        params={"name": "Silicon", "ownerId": OWNER_ID, "limit": 1},
        headers=client.materials.headers,
    )


def test_load_material_raises_when_neither_has_it(tmp_path):
    client = MagicMock()
    client.materials.request.return_value = []

    with pytest.raises(ValueError, match="Germanium"):
        load_material(client, str(tmp_path), "Germanium", OWNER_ID)


def test_load_material_falls_through_a_folder_near_miss(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(SILICON_NAMED))
    (tmp_path / "silicon relaxed.json").write_text(json.dumps({**SILICON_NAMED, "name": "Silicon relaxed"}))
    client = MagicMock()
    client.materials.request.return_value = [SILICON_NAMED]

    material = load_material(client, str(tmp_path), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.request.assert_called_once_with(
        "GET",
        client.materials.name,
        params={"name": "Silicon", "ownerId": OWNER_ID, "limit": 1},
        headers=client.materials.headers,
    )


JOB_ID = "job-1"
FINAL_STRUCTURE_MATERIAL_ID = "m-final-structure"


@pytest.mark.parametrize(
    ("holders", "error"),
    [
        ([{"data": {"materialId": FINAL_STRUCTURE_MATERIAL_ID}}], None),
        ([], "reported no 'final_structure'"),
    ],
)
def test_get_final_structure_for_job(holders, error):
    client = MagicMock()
    client.properties.request.return_value = holders
    client.materials.get.return_value = Materials.get_by_name_first_match("Silicon")
    if error:
        with pytest.raises(RuntimeError, match=error):
            get_final_structure_for_job(client, JOB_ID)
        return
    material = get_final_structure_for_job(client, JOB_ID)
    assert material.basis.elements.values == ["Si", "Si"]
    client.properties.request.assert_called_once_with(
        "GET",
        client.properties.name,
        params={"jobId": JOB_ID, "slug": "final_structure"},
        headers=client.properties.headers,
    )
    client.materials.get.assert_called_once_with(FINAL_STRUCTURE_MATERIAL_ID)
