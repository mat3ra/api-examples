"""Unit tests for bulk-crystal query resolution."""

import pytest
from mat3ra.made.material import Material
from mat3ra.made.tools.analyze.lattice_planes import CrystalLatticePlanesMaterialAnalyzer
from mat3ra.made.tools.helpers import create_slab
from mat3ra.notebooks_utils.core.entity.material.analysis import get_slab_bulk_crystal, resolve_bulk_query_from_crystal
from mat3ra.standata.materials import Materials

SILICON = Materials.get_by_name_first_match("Silicon")


@pytest.mark.parametrize(
    "extra_keys,expected",
    [
        (
            {"scaledHash": "scaled-hash-value", "hash": "hash-value", "_id": "material-id"},
            {"scaledHash": "scaled-hash-value"},
        ),
        ({"hash": "hash-value", "_id": "material-id"}, {"hash": "hash-value"}),
        ({"_id": "material-id"}, {"_id": "material-id"}),
    ],
)
def test_resolve_bulk_query_prefers_scaled_hash_then_hash_then_id(extra_keys, expected):
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
