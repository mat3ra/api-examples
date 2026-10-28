"""Unit tests for bulk-crystal query resolution."""

import numpy as np
import pytest
from mat3ra.made.material import Material
from mat3ra.made.tools.analyze.lattice_planes import CrystalLatticePlanesMaterialAnalyzer
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum
from mat3ra.made.tools.helpers import create_interface_simple, create_slab
from mat3ra.made.tools.modify import interface_displace_part, interface_get_part
from mat3ra.notebooks_utils.core.entity.material.analysis import (
    get_interface_part_by_z_split,
    get_slab_bulk_crystal,
    resolve_bulk_query_from_crystal,
    translate_slab_to_z_center,
)
from mat3ra.standata.materials import Materials

SILICON = Materials.get_by_name_first_match("Silicon")
GERMANIUM = Material.create(Materials.get_by_name_first_match("Germanium"))
INTERFACE = create_interface_simple(Material.create(SILICON), GERMANIUM)
FILM_LOWERED = interface_displace_part(INTERFACE, [0, 0, -0.5], InterfacePartsEnum.FILM)
SUBSTRATE_LOWERED_AND_WRAPPED = interface_displace_part(INTERFACE, [0, 0, -0.3], InterfacePartsEnum.SUBSTRATE)


@pytest.mark.parametrize(
    "extra_keys,expected",
    [
        (
            {"scaledHash": "scaled-hash-value", "hash": "hash-value", "_id": "material-id"},
            {"_id": "material-id"},
        ),
        ({"scaledHash": "scaled-hash-value", "hash": "hash-value"}, {"hash": "hash-value"}),
        ({"scaledHash": "scaled-hash-value"}, {"scaledHash": "scaled-hash-value"}),
    ],
)
def test_resolve_bulk_query_prefers_id_then_hash_then_scaled_hash(extra_keys, expected):
    assert resolve_bulk_query_from_crystal({**SILICON, **extra_keys}) == expected


def test_resolve_bulk_query_computes_hash_when_none_present():
    query = resolve_bulk_query_from_crystal(SILICON)
    assert set(query) == {"hash"}
    assert query["hash"]


def test_slab_bulk_crystal_is_the_material_the_slab_was_built_from():
    """
    A slab built from a primitive bulk must resolve back to that primitive bulk, not to the
    conventional cell -- otherwise the Total Energy job run on the input is unreachable and
    surface energy combines a slab SCF with a bulk reference from a different cell.
    """
    primitive = Material.create(Materials.get_by_name_first_match("Nickel"))
    conventional = CrystalLatticePlanesMaterialAnalyzer(
        material=primitive, miller_indices=(0, 0, 1)
    ).material_with_conventional_lattice
    assert conventional.hash != primitive.hash

    slab = create_slab(crystal=primitive, miller_indices=(0, 0, 1), number_of_layers=3)

    assert get_slab_bulk_crystal(slab)["hash"] == primitive.hash


@pytest.mark.parametrize("labelled_structure", [INTERFACE, FILM_LOWERED, SUBSTRATE_LOWERED_AND_WRAPPED])
@pytest.mark.parametrize("part", [InterfacePartsEnum.SUBSTRATE, InterfacePartsEnum.FILM])
def test_get_interface_part_by_z_split(labelled_structure, part):
    structure = Material.create({**labelled_structure.to_dict(), "metadata": {}})
    structure.basis.set_labels_from_list([])
    structure.to_cartesian()
    centered_structure = translate_slab_to_z_center(structure)
    expected = interface_get_part(translate_slab_to_z_center(labelled_structure), part)
    result = get_interface_part_by_z_split(translate_slab_to_z_center(INTERFACE), centered_structure, part)
    heights = [z for _, _, z in centered_structure.basis.coordinates.values]

    assert min(heights) + max(heights) == pytest.approx(1)
    assert result.basis.elements.values == expected.basis.elements.values
    assert np.allclose(result.basis.coordinates.values, expected.basis.coordinates.values)
