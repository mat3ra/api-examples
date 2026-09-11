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


def cartesian_positions(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.coordinates_array)


def test_relax_material_lowers_the_energy_and_keeps_identity():
    relaxed = relax_material(MATERIAL, CALCULATOR, **RELAX)
    assert calculate_total_energy(relaxed, CALCULATOR) < calculate_total_energy(MATERIAL, CALCULATOR)
    assert relaxed.name == MATERIAL.name
    assert relaxed.basis.labels.values == MATERIAL.basis.labels.values
    assert relaxed.basis.is_in_crystal_units == MATERIAL.basis.is_in_crystal_units


def test_relax_material_holds_fixed_atoms_and_z_only_motion():
    fixed = [0]  # bottom Ni of the fixture
    relaxed = relax_material(MATERIAL, CALCULATOR, fixed_atom_indices=fixed, along_z_only=True, **RELAX)
    before, after = cartesian_positions(MATERIAL), cartesian_positions(relaxed)
    assert np.allclose(after[fixed], before[fixed])
    assert np.allclose(after[:, :2], before[:, :2], atol=1e-6)
    assert not np.allclose(after[:, 2], before[:, 2])


def test_relax_material_raises_when_not_converged():
    with pytest.raises(RuntimeError):
        relax_material(MATERIAL, CALCULATOR, fmax=1e-6, max_steps=1, logfile=None)
