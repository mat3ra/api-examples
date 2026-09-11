from typing import Final

import numpy as np
import pytest
from ase.calculators.emt import EMT
from mat3ra.made.material import Material
from mat3ra.made.tools.calculate import calculate_total_energy
from mat3ra.notebooks_utils.mlff.relaxation import relax_material

from .fixtures_gr_ni import GRAPHENE_NICKEL_TOP_HCP

MATERIAL: Final = Material.create(GRAPHENE_NICKEL_TOP_HCP)
CALCULATOR: Final = EMT()
RELAX: Final = {"fmax": 0.1, "max_steps": 50, "logfile": None}

CASES = [
    # (fixed_atom_indices, along_z_only, expected)
    ([], False, {"fixed": [], "xy_unchanged": True}),
    ([0], True, {"fixed": [0], "xy_unchanged": True}),  # bottom Ni of the fixture
]


def _cartesian_positions(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.coordinates_array)


@pytest.mark.parametrize("fixed_atom_indices, along_z_only, expected", CASES)
def test_relax_material(fixed_atom_indices, along_z_only, expected):
    relaxed = relax_material(
        MATERIAL, CALCULATOR, fixed_atom_indices=fixed_atom_indices, along_z_only=along_z_only, **RELAX
    )
    assert calculate_total_energy(relaxed, CALCULATOR) < calculate_total_energy(MATERIAL, CALCULATOR)
    assert relaxed.name == MATERIAL.name
    assert relaxed.basis.labels.values == MATERIAL.basis.labels.values
    assert relaxed.basis.is_in_crystal_units == MATERIAL.basis.is_in_crystal_units

    before, after = _cartesian_positions(MATERIAL), _cartesian_positions(relaxed)
    assert np.allclose(after[expected["fixed"]], before[expected["fixed"]])
    assert np.allclose(after[:, :2], before[:, :2], atol=1e-6) == expected["xy_unchanged"]


def test_relax_material_invalid():
    with pytest.raises(RuntimeError):
        relax_material(MATERIAL, CALCULATOR, fmax=1e-6, max_steps=1, logfile=None)
