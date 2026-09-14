import pytest
from mat3ra.made.material import Material
from mat3ra.made.tools.helpers import SurfaceSiteAnalyzer, create_slab
from mat3ra.made.tools.modify import interface_label_parts_by_elements
from mat3ra.notebooks_utils.interface import buckling_text, film_sites_and_buckling, registry_cell
from mat3ra.standata.materials import Materials

NICKEL_111 = create_slab(
    crystal=Material.create(Materials.get_by_name_first_match("Nickel")),
    miller_indices=(1, 1, 1),
    number_of_layers=3,
    vacuum=15.0,
)
ANALYZER = SurfaceSiteAnalyzer(material=NICKEL_111)

_cartesian = NICKEL_111.clone()
_cartesian.to_cartesian()
Z_TOP = max(c[2] for c in _cartesian.coordinates_array)


def _labelled(sites_and_heights):
    """A film of one carbon per (site name, height above the surface), on this Ni(111) slab."""
    material = NICKEL_111.clone()
    for site_name, height in sites_and_heights:
        x, y, _ = NICKEL_111.basis.cell.convert_point_to_cartesian(ANALYZER.sites[site_name][0])
        material.add_atom("C", [x, y, Z_TOP + height], use_cartesian_coordinates=True)
    return interface_label_parts_by_elements(material, substrate_elements={"Ni"})


ATOP_AND_HCP = _labelled([("atop", 2.0), ("hcp", 1.7)])
FCC_AND_HCP = _labelled([("fcc", 1.8), ("hcp", 1.9)])


@pytest.mark.parametrize(
    "interface,expected_sites,expected_buckling",
    [
        (ATOP_AND_HCP, {"atop", "hcp"}, 0.3),
        (FCC_AND_HCP, {"fcc", "hcp"}, None),
    ],
)
def test_film_sites_and_buckling(interface, expected_sites, expected_buckling):
    sites, buckling = film_sites_and_buckling(interface)
    assert sites == expected_sites
    if expected_buckling is None:
        assert buckling is None
    else:
        assert buckling == pytest.approx(expected_buckling)


@pytest.mark.parametrize(
    "buckling,expected",
    [
        (None, "   —   "),
        (0.003, "+0.003"),
        (-0.012, "-0.012"),
    ],
)
def test_buckling_text(buckling, expected):
    assert buckling_text(buckling) == expected


@pytest.mark.parametrize(
    "label,result,expected",
    [
        ("atop_fcc", {"drifted": False, "sites": {"atop", "fcc"}}, "atop_fcc"),
        ("atop_hcp", {"drifted": True, "sites": {None, "atop"}}, "atop_hcp→None/atop"),
        ("hollow", {"drifted": True, "sites": {"fcc", "hcp"}}, "hollow→fcc/hcp"),
    ],
)
def test_registry_cell(label, result, expected):
    assert registry_cell(label, result) == expected
