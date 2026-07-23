"""Unit tests for bulk-crystal query resolution."""

import pytest
from mat3ra.notebooks_utils.core.entity.material.analysis import resolve_bulk_query_from_crystal
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
