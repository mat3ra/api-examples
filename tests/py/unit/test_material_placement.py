from typing import Final, List

import numpy as np
import pytest
from mat3ra.made.material import Material
from mat3ra.made.tools.build_components.entities.reusable.three_dimensional.supercell.helpers import create_supercell
from mat3ra.notebooks_utils.material.placement import (
    describe_atoms,
    get_atom_index,
    get_atom_indices,
    get_film_site_occupation,
    place_over,
)

from .fixtures_gr_ni import GRAPHENE_NICKEL_TOP_HCP

MOS2: Final = {
    "name": "MoS2 monolayer",
    "basis": {
        "elements": [{"id": 0, "value": "Mo"}, {"id": 1, "value": "S"}, {"id": 2, "value": "S"}],
        "coordinates": [
            {"id": 0, "value": [0.3333, 0.6667, 0.5]},
            {"id": 1, "value": [0.6667, 0.3333, 0.42]},
            {"id": 2, "value": [0.6667, 0.3333, 0.58]},
        ],
        "units": "crystal",
    },
    "lattice": {
        "a": 3.19,
        "b": 3.19,
        "c": 20.0,
        "alpha": 90,
        "beta": 90,
        "gamma": 120,
        "units": {"length": "angstrom", "angle": "degree"},
        "type": "HEX",
    },
}
INTERFACE: Final = Material.create(GRAPHENE_NICKEL_TOP_HCP)  # Ni 0-2 (2 is the top layer), C 3 (atop), C 4 (hcp)


def top_nickel(supercell: Material) -> List[int]:
    cartesian = supercell.clone()
    cartesian.to_cartesian()
    z = np.array(cartesian.coordinates_array)[:, 2]
    nickel = [i for i, e in enumerate(supercell.basis.elements.values) if e == "Ni"]
    return [i for i in nickel if z[i] > z[nickel].max() - 0.5]


def far_apart(supercell: Material, atoms: List[int], count: int) -> List[int]:
    """`count` atoms of the list chosen greedily to be as far from one another as periodicity allows."""
    cartesian = supercell.clone()
    cartesian.to_cartesian()
    xy = np.array(cartesian.coordinates_array)[:, :2]
    vectors = np.array(supercell.lattice.vector_arrays)[:2, :2]
    shifts = [i * vectors[0] + j * vectors[1] for i in (-1, 0, 1) for j in (-1, 0, 1)]

    def distance(a, b):
        return min(np.linalg.norm(xy[a] + s - xy[b]) for s in shifts)

    chosen = [atoms[0]]
    while len(chosen) < count:
        chosen.append(max((a for a in atoms if a not in chosen), key=lambda a: min(distance(a, c) for c in chosen)))
    return chosen


def test_get_atom_indices_by_element():
    mos2 = Material.create(MOS2)
    assert get_atom_indices(mos2, "S") == [1, 2]
    assert get_atom_indices(mos2) == [0, 1, 2]


def test_get_atom_indices_within_a_radius_of_a_coordinate_nearest_first():
    mos2 = Material.create(MOS2)
    assert get_atom_indices(mos2, "S", coordinate=[0.6667, 0.3333, 0.45], radius=1.0) == [1]
    assert get_atom_indices(mos2, "S", coordinate=[0.6667, 0.3333, 0.45], radius=3.0) == [1, 2]
    assert get_atom_indices(mos2, "S", coordinate=[0.6667, 0.3333, 0.45], radius=0.1) == []


def test_get_atom_index_points_at_the_element_near_a_coordinate():
    mos2 = Material.create(MOS2)
    assert get_atom_index(mos2, "Mo", coordinate=[0.25, 0.75, 0.5], radius=1.0) == 0
    assert get_atom_index(mos2, "S", coordinate=[0.6, 0.3, 0.42], radius=1.0) == 1
    assert get_atom_index(mos2, "S", coordinate=[0.6, 0.3, 0.58], radius=1.0) == 2


def test_get_atom_index_says_how_far_the_nearest_is_when_none_qualifies():
    with pytest.raises(ValueError, match=r"No Mo within 0.5 A .* nearest Mo is 1\.\d\d A away"):
        get_atom_index(Material.create(MOS2), "Mo", coordinate=[0.0, 0.0, 0.5], radius=0.5)


def test_describe_atoms_shows_what_was_chosen():
    described = describe_atoms(Material.create(MOS2), [0])
    assert described[0]["element"] == "Mo" and described[0]["index"] == 0
    assert described[0]["coordinate"][:2] == [0.3333, 0.6667]


def test_place_over_one_substrate_atom_is_atop():
    placed = place_over(INTERFACE, film_atom=4, substrate_atoms=[2])
    assert get_film_site_occupation(placed)[4] == "atop"


def test_place_over_three_neighbours_is_a_hollow():
    supercell = create_supercell(INTERFACE, scaling_factor=[2, 2, 1])
    carbon = next(i for i, e in enumerate(supercell.basis.elements.values) if e == "C")
    placed = place_over(supercell, film_atom=carbon, substrate_atoms=top_nickel(supercell)[:3])
    assert get_film_site_occupation(placed)[carbon] in ("fcc", "hcp")


def test_place_over_two_neighbours_is_a_bridge():
    supercell = create_supercell(INTERFACE, scaling_factor=[2, 2, 1])
    carbon = next(i for i, e in enumerate(supercell.basis.elements.values) if e == "C")
    placed = place_over(supercell, film_atom=carbon, substrate_atoms=top_nickel(supercell)[:2])
    assert get_film_site_occupation(placed)[carbon] == "bridge"


def test_place_over_rejects_atoms_that_are_not_one_site():
    supercell = create_supercell(INTERFACE, scaling_factor=[4, 4, 1])
    carbon = next(i for i, e in enumerate(supercell.basis.elements.values) if e == "C")
    with pytest.raises(ValueError, match="not one site's neighbours"):
        place_over(supercell, film_atom=carbon, substrate_atoms=far_apart(supercell, top_nickel(supercell), 3))


def test_place_over_rejects_wrong_parts():
    with pytest.raises(ValueError, match="not in the film"):
        place_over(INTERFACE, film_atom=0, substrate_atoms=[2])
    with pytest.raises(ValueError, match="Not all"):
        place_over(INTERFACE, film_atom=3, substrate_atoms=[4])
