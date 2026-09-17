import json

from mat3ra.notebooks_utils.core.entity.material.io import load_material_from_folder, load_materials_from_folder
from mat3ra.standata.materials import Materials

RADII = {"Si": 1.11, "C": 0.76}


def _uploads_folder(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(Materials.get_by_name_first_match("Silicon")))
    (tmp_path / "radii.json").write_text(json.dumps(RADII))
    return str(tmp_path)


def test_data_file_beside_a_material_is_skipped(tmp_path):
    assert len(load_materials_from_folder(_uploads_folder(tmp_path), verbose=False)) == 1


def test_lookup_by_name_works_alongside_a_data_file(tmp_path):
    assert load_material_from_folder(_uploads_folder(tmp_path), "Silicon", verbose=False) is not None
