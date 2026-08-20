import json
from typing import Any, Dict

from mat3ra.notebooks_utils.core.entity.material.io import load_material_from_folder, load_materials_from_folder

SILICON: Dict[str, Any] = {
    "name": "Silicon",
    "lattice": {
        "a": 3.867,
        "b": 3.867,
        "c": 3.867,
        "alpha": 60.0,
        "beta": 60.0,
        "gamma": 60.0,
        "units": {"length": "angstrom", "angle": "degree"},
        "type": "FCC",
    },
    "basis": {
        "elements": [{"id": 0, "value": "Si"}, {"id": 1, "value": "Si"}],
        "coordinates": [{"id": 0, "value": [0.0, 0.0, 0.0]}, {"id": 1, "value": [0.25, 0.25, 0.25]}],
        "units": "crystal",
    },
}

# The kind of file a user script reads - valid JSON, not a material.
RADII: Dict[str, Any] = {"Si": 1.11, "C": 0.76}


def _write(folder, name, payload):
    path = folder / name
    path.write_text(json.dumps(payload))
    return path


def test_non_material_json_is_skipped_not_fatal(tmp_path):
    """A data file beside the materials must not fail the whole load."""
    _write(tmp_path, "silicon.json", SILICON)
    _write(tmp_path, "radii.json", RADII)

    materials = load_materials_from_folder(str(tmp_path), verbose=False)

    assert [material.name for material in materials] == ["Silicon"]


def test_lookup_by_name_still_works_alongside_a_data_file(tmp_path):
    _write(tmp_path, "silicon.json", SILICON)
    _write(tmp_path, "radii.json", RADII)

    assert load_material_from_folder(str(tmp_path), "Silicon", verbose=False).name == "Silicon"


def test_folder_of_only_data_files_yields_nothing(tmp_path):
    _write(tmp_path, "radii.json", RADII)

    assert load_materials_from_folder(str(tmp_path), verbose=False) == []
