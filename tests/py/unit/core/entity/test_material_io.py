import json
from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.material.io import (
    load_material,
    load_material_from_folder,
    load_materials_from_folder,
)
from mat3ra.standata.materials import Materials

RADII = {"Si": 1.11, "C": 0.76}
OWNER_ID = "account-1"


def _uploads_folder(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(Materials.get_by_name_first_match("Silicon")))
    (tmp_path / "radii.json").write_text(json.dumps(RADII))
    return str(tmp_path)


def test_data_file_beside_a_material_is_skipped(tmp_path):
    assert len(load_materials_from_folder(_uploads_folder(tmp_path), verbose=False)) == 1


def test_lookup_by_name_works_alongside_a_data_file(tmp_path):
    assert load_material_from_folder(_uploads_folder(tmp_path), "Silicon", verbose=False) is not None


SILICON_NAMED = {**Materials.get_by_name_first_match("Silicon"), "name": "Silicon"}


def test_load_material_finds_an_exact_match_in_the_folder(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(SILICON_NAMED))
    client = MagicMock()

    material = load_material(client, str(tmp_path), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.list.assert_not_called()


def test_load_material_falls_back_to_the_account(tmp_path):
    client = MagicMock()
    client.materials.list.return_value = [SILICON_NAMED]

    material = load_material(client, _uploads_folder(tmp_path), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.list.assert_called_once_with({"name": "Silicon", "owner._id": OWNER_ID}, {"limit": 1})


def test_load_material_raises_when_neither_has_it(tmp_path):
    client = MagicMock()
    client.materials.list.return_value = []

    with pytest.raises(ValueError, match="Germanium"):
        load_material(client, _uploads_folder(tmp_path), "Germanium", OWNER_ID)


def test_load_material_falls_through_a_folder_near_miss(tmp_path):
    folder = tmp_path
    (folder / "silicon.json").write_text(json.dumps(SILICON_NAMED))
    (folder / "silicon relaxed.json").write_text(json.dumps({**SILICON_NAMED, "name": "Silicon relaxed"}))
    client = MagicMock()
    client.materials.list.return_value = [SILICON_NAMED]

    material = load_material(client, str(folder), "Silicon", OWNER_ID)

    assert material.name == "Silicon"
    client.materials.list.assert_called_once_with({"name": "Silicon", "owner._id": OWNER_ID}, {"limit": 1})
