from typing import Final

import numpy as np
import pytest
from ase.calculators.emt import EMT
from mat3ra.made.material import Material
from mat3ra.made.tools.calculate import calculate_total_energy
from mat3ra.notebooks_utils.mlff.relaxation import relax_material

from .fixtures_gr_ni import GRAPHENE_NICKEL_CARBON_DISPLACED, GRAPHENE_NICKEL_TOP_HCP

MATERIAL: Final = Material.create(GRAPHENE_NICKEL_TOP_HCP)
CARBON_DISPLACED: Final = Material.create(GRAPHENE_NICKEL_CARBON_DISPLACED)
CALCULATOR: Final = EMT()
RELAX: Final = {"fmax": 0.1, "max_steps": 50, "logfile": None}

CASES = [
    # (material, fixed_atom_indices, along_z_only, xy_unchanged)
    (MATERIAL, [], False, True),
    (MATERIAL, [0], True, True),  # bottom Ni of the fixture, no in-plane force to constrain
    (CARBON_DISPLACED, [0], False, False),  # in-plane force free to act: the carbon drifts back
    (CARBON_DISPLACED, [0], True, True),  # same force, held to z: the carbon cannot drift
]


def _cartesian_positions(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.coordinates_array)


@pytest.mark.parametrize("material, fixed_atom_indices, along_z_only, xy_unchanged", CASES)
def test_relax_material(material, fixed_atom_indices, along_z_only, xy_unchanged):
    relaxed = relax_material(
        material, CALCULATOR, fixed_atom_indices=fixed_atom_indices, along_z_only=along_z_only, **RELAX
    )
    assert calculate_total_energy(relaxed, CALCULATOR) < calculate_total_energy(material, CALCULATOR)
    assert relaxed.name == material.name
    assert relaxed.basis.labels.values == material.basis.labels.values
    assert relaxed.basis.is_in_crystal_units == material.basis.is_in_crystal_units

    before, after = _cartesian_positions(material), _cartesian_positions(relaxed)
    assert np.allclose(after[fixed_atom_indices], before[fixed_atom_indices])
    assert np.allclose(after[:, :2], before[:, :2], atol=1e-6) == xy_unchanged


def test_relax_material_invalid():
    with pytest.raises(RuntimeError):
        relax_material(MATERIAL, CALCULATOR, fmax=1e-6, max_steps=1, logfile=None)
