import numpy as np
import pytest
from mat3ra.made.material import Material
from mat3ra.notebooks_utils.core.entity.material.modify import translate_atoms

LATTICE_VECTORS = [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 20.0]]

MATERIAL_CONFIG = {
    "name": "test-slab",
    "lattice": {
        "a": 4.0,
        "b": 4.0,
        "c": 20.0,
        "alpha": 90.0,
        "beta": 90.0,
        "gamma": 90.0,
        "units": {"length": "angstrom", "angle": "degree"},
        "type": "TRI",
        "vectors": {
            "a": LATTICE_VECTORS[0],
            "b": LATTICE_VECTORS[1],
            "c": LATTICE_VECTORS[2],
            "alat": 1,
            "units": "angstrom",
        },
    },
    "basis": {
        "elements": [{"id": 0, "value": "Si"}, {"id": 1, "value": "Si"}, {"id": 2, "value": "Si"}],
        "coordinates": [
            {"id": 0, "value": [0.0, 0.0, 0.20]},
            {"id": 1, "value": [0.5, 0.5, 0.50]},
            {"id": 2, "value": [0.0, 0.5, 0.80]},
        ],
        "units": "crystal",
        "cell": {"a": LATTICE_VECTORS[0], "b": LATTICE_VECTORS[1], "c": LATTICE_VECTORS[2]},
    },
}


@pytest.fixture
def material():
    return Material.create(MATERIAL_CONFIG)


def test_translate_atoms_moves_only_the_named_atom(material):
    moved = translate_atoms(material, 1, [0.0, 0.0, -2.0])

    assert moved.coordinates_array[0] == material.coordinates_array[0]
    assert moved.coordinates_array[2] == material.coordinates_array[2]
    assert moved.coordinates_array[1] != material.coordinates_array[1]


def test_translate_atoms_cartesian_vector_is_angstrom(material):
    moved = translate_atoms(material, 1, [0.0, 0.0, -2.0])

    displacement = (np.array(moved.coordinates_array[1]) - np.array(material.coordinates_array[1])) @ np.array(
        LATTICE_VECTORS
    )
    assert np.linalg.norm(displacement) == pytest.approx(2.0)


def test_translate_atoms_crystal_vector_is_fractional(material):
    moved = translate_atoms(material, 1, [0.0, 0.0, -0.1], use_cartesian_coordinates=False)

    assert moved.coordinates_array[1][2] == pytest.approx(0.4)


def test_translate_atoms_accepts_several_indices(material):
    moved = translate_atoms(material, [0, 2], [0.0, 0.0, 1.0])

    assert moved.coordinates_array[1] == material.coordinates_array[1]
    assert moved.coordinates_array[0][2] > material.coordinates_array[0][2]
    assert moved.coordinates_array[2][2] > material.coordinates_array[2][2]


def test_translate_atoms_does_not_mutate_the_input(material):
    before = [list(coordinate) for coordinate in material.coordinates_array]

    translate_atoms(material, 1, [0.0, 0.0, -2.0])

    assert [list(coordinate) for coordinate in material.coordinates_array] == before


def test_translate_atoms_rejects_an_index_outside_the_basis(material):
    with pytest.raises(IndexError, match="out of range"):
        translate_atoms(material, 7, [0.0, 0.0, -1.0])
