import numpy as np
import pytest
from ase.calculators.emt import EMT
from mat3ra.made.material import Material
from mat3ra.made.tools.calculate import calculate_total_energy
from mat3ra.made.tools.helpers import create_slab, get_atom_indices_by_layer
from mat3ra.notebooks_utils.relaxation import relax_material
from mat3ra.standata.materials import Materials

# A plain slab, not an interface: relax_material's contract is about constraints (fixed atoms,
# along_z_only, non-convergence), not about Gr/Ni physics, and the interface path is already
# covered by scripts/verify_fast_tier.py and by made's own tests. Ni(100), not (111): its surface
# relaxation force (~0.12 eV/A) already exceeds RELAX's fmax, so no displacement is needed to give
# case 0 a real force to relax.
MATERIAL = create_slab(
    crystal=Material.create(Materials.get_by_name_first_match("Nickel")),
    miller_indices=(1, 0, 0),
    number_of_layers=4,
    vacuum=10.0,
)
_layers = get_atom_indices_by_layer(MATERIAL)
BOTTOM_LAYER = _layers[0]
DISPLACED_ATOM = _layers[-1][0]

_cartesian = MATERIAL.clone()
_cartesian.to_cartesian()
_coordinates = _cartesian.coordinates_array
_coordinates[DISPLACED_ATOM][0] += 0.3
_cartesian.set_coordinates(_coordinates)
_cartesian.to_crystal()
DISPLACED = _cartesian

CALCULATOR = EMT()
RELAX = {"fmax": 0.1, "max_steps": 50, "logfile": None}

CASES = [
    # (material, fixed_atom_indices, along_z_only, xy_unchanged)
    (MATERIAL, BOTTOM_LAYER, True, True),
    (DISPLACED, BOTTOM_LAYER, False, False),  # in-plane force free to act: the atom drifts back
    (DISPLACED, BOTTOM_LAYER, True, True),  # same force, held to z: the atom cannot drift
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
