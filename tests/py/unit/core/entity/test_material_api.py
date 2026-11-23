import json
import re
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from mat3ra.made.material import Material
from mat3ra.notebooks_utils.core.entity.job.api import get_kgrid_query
from mat3ra.notebooks_utils.core.entity.material.api import (
    find_relaxed_material,
    get_final_structure_for_job,
    load_material,
    select_material_by_name,
)
from mat3ra.standata.materials import Materials

OWNER_ID = "account-1"

SILICON = "Silicon"
SILICON_RELAXED = "Silicon relaxed"
SILICON_SUPERCELL = "Silicon 2x2x2"
GERMANIUM_STANDATA_NAME = Materials.get_by_name_first_match("Germanium")["name"]


def _silicon_named(name: str) -> Dict[str, Any]:
    return {**Materials.get_by_name_first_match("Silicon"), "name": name}


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
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-relaxed"}]
    client.materials.get.return_value = RELAXED_MATERIAL_DOC

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    client.materials.list.assert_called_once_with({"hash": DEFECTIVE_HASH, "owner._id": OWNER_ID})
    client.jobs.list.assert_called_once_with(
        {"_material._id": {"$in": [SAVED_DEFECTIVE["_id"]]}, "owner._id": OWNER_ID, "status": "finished"}
    )
    client.properties.get_for_job.assert_called_once_with(FINISHED_JOB["_id"], "final_structure")
    client.materials.get.assert_called_once_with("m-relaxed")


def test_find_relaxed_material_uses_the_last_final_structure_entry():
    # A relaxation job's final_structure property can carry more than one entry: the initial
    # structure (same hash as the input) first, the relaxed one last -- PLAN #27.
    client = MagicMock()
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = [FINISHED_JOB]
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
    client.materials.list.return_value = []
    client.jobs.list.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    assert client.jobs.list.call_args.args[0]["_material._id"] == {"$in": []}


def test_find_relaxed_material_returns_none_when_no_job_exists():
    client = MagicMock()
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    client.properties.get_for_job.assert_not_called()


def test_find_relaxed_material_returns_none_when_job_has_no_final_structure():
    client = MagicMock()
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = []

    assert find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID) is None
    client.materials.get.assert_not_called()


def test_find_relaxed_material_checks_every_same_hash_material():
    other_material: Dict[str, Any] = {"_id": "m-other", "name": "B-vacancy h-BN", "hash": DEFECTIVE_HASH}
    client = MagicMock()
    client.materials.list.return_value = [other_material, SAVED_DEFECTIVE]
    client.jobs.list.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-relaxed"}]
    client.materials.get.return_value = RELAXED_MATERIAL_DOC

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    client.jobs.list.assert_called_once_with(
        {"_material._id": {"$in": ["m-other", "m-defective"]}, "owner._id": OWNER_ID, "status": "finished"}
    )


def test_find_relaxed_material_skips_a_final_structure_with_the_same_hash():
    scf_job: Dict[str, Any] = {"_id": "job-scf", "name": "Total Energy", "status": "finished"}
    relax_job: Dict[str, Any] = {"_id": "job-relax", "name": "Fixed-cell Relaxation", "status": "finished"}
    client = MagicMock()
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = [scf_job, relax_job]
    client.properties.get_for_job.side_effect = [[{"materialId": "m-scf"}], [{"materialId": "m-relaxed"}]]
    client.materials.get.side_effect = [SCF_MATERIAL_DOC, RELAXED_MATERIAL_DOC]

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID)

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    assert client.properties.get_for_job.call_count == 2


def test_find_relaxed_material_matches_the_relaxation_kgrid():
    client = MagicMock()
    client.materials.list.return_value = [SAVED_DEFECTIVE]
    client.jobs.list.return_value = [FINISHED_JOB]
    client.properties.get_for_job.return_value = [{"materialId": "m-relaxed"}]
    client.materials.get.return_value = RELAXED_MATERIAL_DOC

    relaxed = find_relaxed_material(client, DEFECTIVE_MATERIAL, OWNER_ID, kgrid=[4, 4, 4], unit_name="pw_vc-relax")

    assert relaxed is not None
    assert relaxed.name == "B-vacancy h-BN relaxed"
    assert get_kgrid_query([4, 4, 4], "pw_vc-relax").items() <= client.jobs.list.call_args.args[0].items()


@pytest.mark.parametrize(
    ("folder_names", "account_names", "name", "expected_name"),
    [
        ([SILICON, SILICON_RELAXED], [], SILICON, SILICON),
        ([], [SILICON_SUPERCELL, SILICON], SILICON, SILICON),
        ([], [SILICON_RELAXED], "relaxed", SILICON_RELAXED),
        ([SILICON_RELAXED], [SILICON_RELAXED], "RELAXED", SILICON_RELAXED),
        ([SILICON], [], "Germanium", GERMANIUM_STANDATA_NAME),
    ],
)
def test_load_material_takes_the_exact_name_or_a_unique_partial_one(
    tmp_path, folder_names, account_names, name, expected_name
):
    for index, folder_name in enumerate(folder_names):
        (tmp_path / f"material-{index}.json").write_text(json.dumps(_silicon_named(folder_name)))
    client = MagicMock()
    client.materials.list.return_value = [_silicon_named(account_name) for account_name in account_names]

    material = load_material(client, str(tmp_path), name, OWNER_ID)

    assert material.name == expected_name
    assert client.materials.list.call_args.args[0] == {
        "name": {"$regex": re.escape(name), "$options": "i"},
        "owner._id": OWNER_ID,
    }


@pytest.mark.parametrize(
    ("folder_names", "account_names", "name", "error"),
    [
        ([], [], "Unobtainium", "No matches found for name 'Unobtainium'"),
        ([SILICON_RELAXED], [SILICON_SUPERCELL], "Silicon ", "matches 2 materials"),
    ],
)
def test_load_material_raises_when_the_name_is_missing_or_ambiguous(tmp_path, folder_names, account_names, name, error):
    for index, folder_name in enumerate(folder_names):
        (tmp_path / f"material-{index}.json").write_text(json.dumps(_silicon_named(folder_name)))
    client = MagicMock()
    client.materials.list.return_value = [_silicon_named(account_name) for account_name in account_names]

    with pytest.raises(ValueError, match=error):
        load_material(client, str(tmp_path), name, OWNER_ID)


JOB_ID = "job-1"
FINAL_STRUCTURE_MATERIAL_ID = "m-final-structure"


@pytest.mark.parametrize(
    ("properties", "error"),
    [
        ([{"materialId": FINAL_STRUCTURE_MATERIAL_ID}], None),
        ([], "reported no 'final_structure'"),
    ],
)
def test_get_final_structure_for_job(properties, error):
    client = MagicMock()
    client.properties.get_for_job.return_value = properties
    client.materials.get.return_value = Materials.get_by_name_first_match("Silicon")
    if error:
        with pytest.raises(RuntimeError, match=error):
            get_final_structure_for_job(client, JOB_ID)
        return
    material = get_final_structure_for_job(client, JOB_ID)
    assert material.basis.elements.values == ["Si", "Si"]
    client.properties.get_for_job.assert_called_once_with(JOB_ID, "final_structure")
    client.materials.get.assert_called_once_with(FINAL_STRUCTURE_MATERIAL_ID)


@pytest.mark.parametrize(
    ("names", "name", "expected_name"),
    [
        ([SILICON_RELAXED, SILICON], SILICON, SILICON),
        ([SILICON_RELAXED], "relaxed", SILICON_RELAXED),
        ([SILICON, SILICON], SILICON, SILICON),
    ],
)
def test_select_material_by_name_takes_the_exact_name_or_a_unique_partial_one(names, name, expected_name):
    material = select_material_by_name([Material.create(_silicon_named(candidate)) for candidate in names], name)

    assert material.name == expected_name


@pytest.mark.parametrize(
    ("names", "name", "error"),
    [
        ([SILICON], "Germanium", "No material named 'Germanium'"),
        ([SILICON_RELAXED, SILICON_SUPERCELL], "Silicon ", "matches 2 materials"),
    ],
)
def test_select_material_by_name_raises_when_the_name_is_missing_or_ambiguous(names, name, error):
    with pytest.raises(ValueError, match=error):
        select_material_by_name([Material.create(_silicon_named(candidate)) for candidate in names], name)
