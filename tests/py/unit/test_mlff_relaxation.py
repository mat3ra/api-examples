import numpy as np
import pytest
from ase.calculators.emt import EMT
from mat3ra.made.material import Material
from mat3ra.made.tools.build.pristine_structures.two_dimensional.slab import SlabBuilder, SlabConfiguration
from mat3ra.made.tools.calculate import calculate_total_energy
from mat3ra.made.tools.helpers import create_interface_zsl_between_slabs
from mat3ra.notebooks_utils.mlff.relaxation import relax_material
from mat3ra.standata.materials import Materials

# Built the same way as optimization_interface_film_xy_position_graphene_nickel.ipynb, cells 1.2-2.3.
_substrate = Material.create(Materials.get_by_name_first_match("Nickel"))
_film = Material.create(Materials.get_by_name_first_match("Graphene"))
_substrate_slab = SlabBuilder().get_material(
    SlabConfiguration.from_parameters(
        material_or_dict=_substrate,
        miller_indices=(1, 1, 1),
        number_of_layers=4,
        vacuum=0.0,
        termination_top_formula=None,
        use_conventional_cell=True,
    )
)
_film_slab = SlabBuilder().get_material(
    SlabConfiguration.from_parameters(
        material_or_dict=_film,
        miller_indices=(0, 0, 1),
        number_of_layers=1,
        vacuum=0.0,
        termination_bottom_formula=None,
        use_conventional_cell=True,
    )
)
MATERIAL = create_interface_zsl_between_slabs(
    substrate_slab=_substrate_slab,
    film_slab=_film_slab,
    gap=2.58,
    vacuum=20.0,
    match_id=0,
    max_area=350,
    max_area_ratio_tol=0.09,
    max_length_tol=0.05,
    max_angle_tol=0.02,
    reduce_result_cell_to_primitive=True,
)
BOTTOM_NI = 0  # lowest z among the substrate's Ni
DISPLACED_CARBON = 4  # a film C; the only fixture with an in-plane force for a relaxation to constrain

CARBON_DISPLACED = MATERIAL.clone()
_coordinates = CARBON_DISPLACED.coordinates_array
_coordinates[DISPLACED_CARBON][0] -= 0.05
CARBON_DISPLACED.set_coordinates(_coordinates)

CALCULATOR = EMT()
RELAX = {"fmax": 0.1, "max_steps": 50, "logfile": None}

CASES = [
    # (material, fixed_atom_indices, along_z_only, xy_unchanged)
    (MATERIAL, [], False, True),
    (MATERIAL, [BOTTOM_NI], True, True),
    (CARBON_DISPLACED, [BOTTOM_NI], False, False),  # in-plane force free to act: the carbon drifts back
    (CARBON_DISPLACED, [BOTTOM_NI], True, True),  # same force, held to z: the carbon cannot drift
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
