import numpy as np
import pytest
from ase.calculators.emt import EMT
from mat3ra.made.material import Material
from mat3ra.made.tools.calculate import calculate_total_energy
from mat3ra.made.tools.helpers import create_slab
from mat3ra.notebooks_utils.workflows.relaxation import relax_material
from mat3ra.standata.materials import Materials

# A plain slab, not an interface: relax_material's contract is about constraints (fixed atoms,
# along_z_only, non-convergence), not about Gr/Ni physics, and the interface path is already
# covered end to end by other/materials_designer/specific_examples/
# optimization_interface_film_xy_position_graphene_nickel_SIMULATION.ipynb and by made's own tests.
# The top atom is displaced deliberately (not left at its built position) so every case tests the
# contract against a real, comfortable force margin rather than however close standata's Ni
# lattice constant happens to sit to EMT's own equilibrium.
LAYER_TOLERANCE = 0.5  # Angstrom: heights closer than this belong to the same layer

MATERIAL = create_slab(
    crystal=Material.create(Materials.get_by_name_first_match("Nickel")),
    miller_indices=(1, 0, 0),
    number_of_layers=4,
    vacuum=10.0,
)

_cartesian = MATERIAL.clone()
_cartesian.to_cartesian()
_z = [c[2] for c in _cartesian.coordinates_array]
BOTTOM_LAYER = [i for i, z in enumerate(_z) if z - min(_z) < LAYER_TOLERANCE]
TOP_ATOM = max(range(len(_z)), key=lambda i: _z[i])


def _displaced(axis: int, amount: float) -> Material:
    displaced = _cartesian.clone()
    coordinates = displaced.coordinates_array
    coordinates[TOP_ATOM][axis] += amount
    displaced.set_coordinates(coordinates)
    displaced.to_crystal()
    return displaced


Z_DISPLACED = _displaced(2, 0.3)  # out-of-plane: a real force for the along_z_only case
XY_DISPLACED = _displaced(0, 0.3)  # in-plane: a real force to hold still or let drift back

CALCULATOR = EMT()
RELAX = {"fmax": 0.1, "max_steps": 50, "logfile": None}

CASES = [
    # (material, fixed_atom_indices, along_z_only, xy_unchanged)
    (Z_DISPLACED, BOTTOM_LAYER, True, True),
    (XY_DISPLACED, BOTTOM_LAYER, False, False),  # in-plane force free to act: the atom drifts back
    (XY_DISPLACED, BOTTOM_LAYER, True, True),  # same force, held to z: the atom cannot drift
]


def _cartesian_positions(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.coordinates_array)


@pytest.mark.parametrize("material, fixed_atom_indices, along_z_only, xy_unchanged", CASES)
# measured (pytest --durations=0): module 4.34s total, slowest case 0.05s
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
