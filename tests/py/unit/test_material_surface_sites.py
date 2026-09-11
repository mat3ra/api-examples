import copy
from typing import Any, Dict, Final

import numpy as np
import pytest
from mat3ra.made.material import Material
from mat3ra.notebooks_utils.material.surface_sites import SurfaceSiteAnalyzer

from .fixtures_gr_ni import GRAPHENE_NICKEL_TOP_HCP, SQUARE_NET


def substrate_of(config: dict) -> Material:
    material = Material.create(config)
    material.basis.filter_atoms_by_labels([0])
    return material


def cartesian_xy(config: dict, atom_index: int) -> np.ndarray:
    material = Material.create(config)
    material.to_cartesian()
    return np.array(material.coordinates_array[atom_index][:2])


def shifted_by_one_cell(config: dict) -> dict:
    """The same substrate with every atom moved by +1 along a — positions on and past the boundary."""
    moved = copy.deepcopy(config)
    for item in moved["basis"]["coordinates"]:
        item["value"] = [item["value"][0] + 1.0, item["value"][1], item["value"][2]]
    return moved


SUBSTRATE: Final = substrate_of(GRAPHENE_NICKEL_TOP_HCP)
ANALYZER: Final = SurfaceSiteAnalyzer(SUBSTRATE)
LATTICE_A: Final = SUBSTRATE.lattice.a
CARBON_ATOP_XY: Final = cartesian_xy(GRAPHENE_NICKEL_TOP_HCP, 3)
CARBON_HCP_XY: Final = cartesian_xy(GRAPHENE_NICKEL_TOP_HCP, 4)
SITE_COUNTS_1X1: Final = {"atop": 1, "bridge": 3, "fcc": 1, "hcp": 1}
RECTANGULAR_NET: Dict[str, Any] = copy.deepcopy(SQUARE_NET)
RECTANGULAR_NET["lattice"]["b"] = 3.0


def site_counts(analyzer: SurfaceSiteAnalyzer) -> dict:
    return {name: len(points) for name, points in analyzer.sites.items()}


def test_sites_of_the_1x1_ni111_cell():
    assert site_counts(ANALYZER) == SITE_COUNTS_1X1


def test_hollows_sit_one_site_step_from_atop():
    atop = np.array(ANALYZER.sites["atop"][0])
    for name in ("fcc", "hcp"):
        shift = np.array(ANALYZER.get_displacement_to_site(atop, name)[:2])
        assert np.isclose(np.linalg.norm(shift), LATTICE_A / np.sqrt(3), atol=1e-3)


@pytest.mark.parametrize("coordinate_xy,expected", [(CARBON_ATOP_XY, "atop"), (CARBON_HCP_XY, "hcp")])
def test_get_site_name(coordinate_xy, expected):
    assert ANALYZER.get_site_name(coordinate_xy) == expected


def test_get_site_name_off_site_is_none():
    atop = np.array(ANALYZER.sites["atop"][0])
    halfway_to_fcc = atop + np.array(ANALYZER.get_displacement_to_site(atop, "fcc")[:2]) / 2
    assert ANALYZER.get_site_name(halfway_to_fcc) is None


def test_get_displacement_to_site_lands_on_it():
    shift = ANALYZER.get_displacement_to_site(CARBON_HCP_XY, "fcc")
    assert shift[2] == 0.0
    assert ANALYZER.get_site_name(CARBON_HCP_XY + np.array(shift[:2])) == "fcc"


def test_atoms_on_or_past_the_cell_boundary_still_count():
    analyzer = SurfaceSiteAnalyzer(substrate_of(shifted_by_one_cell(GRAPHENE_NICKEL_TOP_HCP)))
    assert site_counts(analyzer) == SITE_COUNTS_1X1
    assert analyzer.get_site_name(CARBON_ATOP_XY) == "atop"


def test_sites_do_not_depend_on_basis_order():
    reordered = copy.deepcopy(GRAPHENE_NICKEL_TOP_HCP)
    for key in ("elements", "coordinates", "labels"):
        items = list(reversed(reordered["basis"][key]))
        reordered["basis"][key] = [{"id": i, "value": item["value"]} for i, item in enumerate(items)]
    analyzer = SurfaceSiteAnalyzer(substrate_of(reordered))
    assert site_counts(analyzer) == SITE_COUNTS_1X1
    assert analyzer.get_site_name(CARBON_HCP_XY) == "hcp"


def test_square_net_has_a_four_fold_hollow():
    analyzer = SurfaceSiteAnalyzer(Material.create(SQUARE_NET))
    assert site_counts(analyzer) == {"atop": 1, "bridge": 2, "hollow": 1}
    assert analyzer.get_site_name([1.25, 1.25]) == "hollow"


def test_rectangular_net_keeps_both_bridges():
    assert site_counts(SurfaceSiteAnalyzer(Material.create(RECTANGULAR_NET))) == {"atop": 1, "bridge": 2, "hollow": 1}
