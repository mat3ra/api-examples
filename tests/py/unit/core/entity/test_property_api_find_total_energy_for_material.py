"""Unit tests for find_total_energy_for_material."""

from unittest.mock import MagicMock

import pytest
from mat3ra.notebooks_utils.core.entity.property.api import find_total_energy_for_material

MATERIAL_ID = "material-a"
EXABYTE_ID = "exabyte-a"
MATERIAL = {"_id": MATERIAL_ID, "exabyteId": EXABYTE_ID}
OWNER_ACCOUNT_ID = "account-a"
TOTAL_ENERGY_PROPERTY = {"data": {"value": -12.34}, "precision": {"value": 0.001}}


def _client():
    client = MagicMock()
    client.materials.get.return_value = MATERIAL
    client.properties.request.return_value = [TOTAL_ENERGY_PROPERTY]
    client.my_account.id = OWNER_ACCOUNT_ID
    # entity_cache is often None right after auth -- this must not be relied on.
    client.my_account.entity_cache = None
    return client


def test_find_total_energy_for_material_defaults_to_my_account_scope():
    client = _client()

    result = find_total_energy_for_material(client, MATERIAL_ID)

    client.materials.get.assert_called_once_with(MATERIAL_ID)
    client.properties.request.assert_called_once_with(
        "GET",
        client.properties.name,
        params={
            "exabyteId": EXABYTE_ID,
            "slug": "total_energy",
            "ownerId": OWNER_ACCOUNT_ID,
        },
        headers=client.properties.headers,
    )
    client.jobs.list.assert_not_called()
    assert result == TOTAL_ENERGY_PROPERTY


def test_find_total_energy_for_material_my_account_scope():
    client = _client()

    find_total_energy_for_material(client, MATERIAL_ID, source="my_account")

    client.properties.request.assert_called_once_with(
        "GET",
        client.properties.name,
        params={
            "exabyteId": EXABYTE_ID,
            "slug": "total_energy",
            "ownerId": OWNER_ACCOUNT_ID,
        },
        headers=client.properties.headers,
    )


def test_find_total_energy_for_material_curators_scope():
    client = _client()

    find_total_energy_for_material(client, MATERIAL_ID, source="curators")

    client.properties.request.assert_called_once_with(
        "GET",
        client.properties.name,
        params={
            "exabyteId": EXABYTE_ID,
            "slug": "total_energy",
            "ownerSlug": "curators",
        },
        headers=client.properties.headers,
    )


def test_find_total_energy_for_material_public_scope_has_no_owner_filter():
    client = _client()

    find_total_energy_for_material(client, MATERIAL_ID, source="public")

    client.properties.request.assert_called_once_with(
        "GET",
        client.properties.name,
        params={
            "exabyteId": EXABYTE_ID,
            "slug": "total_energy",
        },
        headers=client.properties.headers,
    )


def test_find_total_energy_for_material_rejects_invalid_source():
    client = _client()

    with pytest.raises(ValueError, match="Invalid source"):
        find_total_energy_for_material(client, MATERIAL_ID, source="everyone")


def test_find_total_energy_for_material_returns_none_when_no_property_found():
    client = _client()
    client.properties.request.return_value = []

    result = find_total_energy_for_material(client, MATERIAL_ID)

    assert result is None


def test_find_total_energy_for_material_returns_none_when_material_has_no_exabyte_id():
    client = _client()
    client.materials.get.return_value = {"_id": MATERIAL_ID}

    result = find_total_energy_for_material(client, MATERIAL_ID)

    client.properties.request.assert_not_called()
    assert result is None
