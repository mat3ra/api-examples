import json

import pytest
from mat3ra.notebooks_utils.core.entity.material.io import load_material_from_folder, load_materials_from_folder
from mat3ra.standata.materials import Materials

RADII = {"Si": 1.11, "C": 0.76}

GRAPHENE_STANDATA_NAME = "C, Graphene, HEX (P6/mmm) 2D (Monolayer), 2dm-3993"
PRISTINE_NAME = "graphene 4x4"
DEFECTIVE_NAME = "graphene 4x4 N3V pyridinic (C28N3)"
RELAXED_NAME = "graphene 4x4 relaxed"

# (filename without extension, material name) pairs; the relaxed material is stored under a
# filename that is not its name.
GRAPHENE_FOLDER = [
    (GRAPHENE_STANDATA_NAME.replace("/", "-"), GRAPHENE_STANDATA_NAME),
    (PRISTINE_NAME, PRISTINE_NAME),
    (DEFECTIVE_NAME, DEFECTIVE_NAME),
    ("pristine graphene", RELAXED_NAME),
]
RENAMED_FILE_FOLDER = [
    (PRISTINE_NAME, RELAXED_NAME),
    (DEFECTIVE_NAME, DEFECTIVE_NAME),
]
RECASED_NAME_FOLDER = [
    (PRISTINE_NAME, PRISTINE_NAME.upper()),
    ("n3v defect", PRISTINE_NAME),
]


def _uploads_folder(tmp_path):
    (tmp_path / "silicon.json").write_text(json.dumps(Materials.get_by_name_first_match("Silicon")))
    (tmp_path / "radii.json").write_text(json.dumps(RADII))
    return str(tmp_path)


def test_data_file_beside_a_material_is_skipped(tmp_path):
    assert len(load_materials_from_folder(_uploads_folder(tmp_path), verbose=False)) == 1


def test_lookup_by_name_works_alongside_a_data_file(tmp_path):
    assert load_material_from_folder(_uploads_folder(tmp_path), "Silicon", verbose=False) is not None


def _material_folder(tmp_path, files):
    for filename, name in files:
        graphene = {**Materials.get_by_name_first_match("Graphene"), "name": name}
        (tmp_path / f"{filename}.json").write_text(json.dumps(graphene))
    return str(tmp_path)


@pytest.mark.parametrize(
    ("files", "requested_name", "expected_name"),
    [
        (GRAPHENE_FOLDER, PRISTINE_NAME, PRISTINE_NAME),
        (GRAPHENE_FOLDER, DEFECTIVE_NAME, DEFECTIVE_NAME),
        (GRAPHENE_FOLDER, "GRAPHENE 4X4", PRISTINE_NAME),
        (GRAPHENE_FOLDER, "N3V", DEFECTIVE_NAME),
        (GRAPHENE_FOLDER, "pristine", RELAXED_NAME),
        (GRAPHENE_FOLDER, "relaxed", RELAXED_NAME),
        (GRAPHENE_FOLDER, "Graphene", GRAPHENE_STANDATA_NAME),
        (GRAPHENE_FOLDER, "Germanium", None),
        (RENAMED_FILE_FOLDER, PRISTINE_NAME, RELAXED_NAME),
        (RENAMED_FILE_FOLDER, "GRAPHENE 4X4", RELAXED_NAME),
        (RECASED_NAME_FOLDER, PRISTINE_NAME, PRISTINE_NAME),
    ],
)
def test_load_material_from_folder(tmp_path, files, requested_name, expected_name):
    material = load_material_from_folder(_material_folder(tmp_path, files), requested_name, verbose=False)

    assert (material.name if material else None) == expected_name
