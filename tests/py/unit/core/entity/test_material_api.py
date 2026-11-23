import json
import re
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from mat3ra.made.material import Material
from mat3ra.notebooks_utils.core.entity.material.api import (
    get_or_create_materials_set,
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


def test_get_or_create_materials_set_takes_saved_material_dicts():
    client = MagicMock()
    client.materials.list.return_value = [{"_id": "set-1", "name": SILICON, "entitySetType": "unordered"}]

    get_or_create_materials_set(client, OWNER_ID, SILICON, [{**_silicon_named(SILICON), "_id": "m-1"}])

    client.materials.move_to_set.assert_called_once_with("m-1", "", "set-1")
