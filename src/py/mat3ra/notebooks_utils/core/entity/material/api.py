import re
from typing import Any, Dict, List, Optional

from mat3ra.api_client import APIClient
from mat3ra.made.material import Material

from .analysis import get_slab_bulk_crystal, resolve_bulk_query_from_crystal

ORDERED_ENTITY_SET_TYPE = "ordered"
UNORDERED_ENTITY_SET_TYPE = "unordered"


def get_or_create_material(api_client: APIClient, material, owner_id: str) -> dict:
    """
    Returns an existing material from the collection if one with the same structural hash
    exists under the given owner, otherwise creates a new one.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        material: mat3ra-made Material object (must have a .hash property).
        owner_id (str): Account ID under which to search and create.

    Returns:
        dict: The material dict (existing or newly created).
    """
    existing = api_client.materials.list({"hash": material.hash, "owner._id": owner_id})
    if existing:
        print(f"♻️  Reusing already existing Material: {existing[0]['_id']}")
        return existing[0]
    created = api_client.materials.create(material.to_dict(), owner_id=owner_id)
    print(f"✅ Material created: {created['_id']}")
    return created


def get_bulk_material(api_client: APIClient, slab_material: Material, owner_id: str) -> Material:
    """
    Resolves the platform bulk material a slab was built from, owned by the given account.

    Args:
        api_client (APIClient): API client instance.
        slab_material (Material): The slab whose bulk material should be resolved.
        owner_id (str): Account ID the resolved bulk material must belong to.

    Returns:
        Material: The resolved bulk material.
    """
    metadata = slab_material.to_dict().get("metadata") or {}
    bulk_query = (
        {"_id": metadata["bulkId"]}
        if metadata.get("bulkId") is not None
        else resolve_bulk_query_from_crystal(get_slab_bulk_crystal(slab_material))
    )
    return _require_material_for_owner(api_client, bulk_query, owner_id)


def get_bulk_material_by_crystal(api_client: APIClient, bulk_crystal: Material, owner_id: str) -> Material:
    """
    Resolves the platform bulk material matching a given bulk crystal, owned by the given account.

    Args:
        api_client (APIClient): API client instance.
        bulk_crystal (Material): The bulk crystal to resolve on the platform.
        owner_id (str): Account ID the resolved bulk material must belong to.

    Returns:
        Material: The resolved bulk material.
    """
    bulk_query = resolve_bulk_query_from_crystal(bulk_crystal.to_dict())
    return _require_material_for_owner(api_client, bulk_query, owner_id)


def _require_material_for_owner(api_client: APIClient, query: dict, owner_id: str) -> Material:
    # Owner belongs in the query, not in a filter over the response: the server truncates, and the
    # account's own material is routinely absent from a page full of other owners' hash twins.
    matches = api_client.materials.list({**query, "owner._id": owner_id})
    material_response = next(iter(matches), None)
    if material_response is None:
        raise ValueError(
            "The bulk material resolved from metadata is not present on the platform for this account. "
            "Run the Total Energy notebook for that bulk material first, then rerun this notebook."
        )
    return Material.create(material_response)


def _index_in_set(material: Dict[str, Any], material_set_id: str) -> float:
    """
    Path-order sort key. A member with no recorded index sorts last, so a
    partially indexed set degrades to "known order first" instead of reshuffling.
    """
    for entry in material.get("inSet") or []:
        if entry.get("_id") == material_set_id:
            index = entry.get("index")
            return float(index) if index is not None else float("inf")
    return float("inf")


def find_material_set(
    api_client: APIClient,
    owner_id: str,
    material_set_name: str,
    require_ordered: bool = False,
) -> Dict[str, Any]:
    """
    Find a materials entity set by name (case-insensitive substring match).

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID that owns the set.
        material_set_name (str): Substring matched against set names under the owner.
        require_ordered (bool): Reject the match unless it carries path order.

    Returns:
        dict: The first matching materials set document.

    Raises:
        ValueError: If no set matches, or if `require_ordered` and the match is unordered.
    """
    material_sets = api_client.materials.list(
        {
            "owner._id": owner_id,
            "isEntitySet": True,
            "name": {"$regex": re.escape(material_set_name), "$options": "i"},
        }
    )
    if not material_sets:
        raise ValueError(f"No material set matching '{material_set_name}'")
    material_set = material_sets[0]

    # Only an ordered set gets inSet.index values, so sorting an unordered one leaves
    # every member tied — an arbitrary path, submitted without an error.
    entity_set_type = material_set.get("entitySetType")
    if require_ordered and entity_set_type != ORDERED_ENTITY_SET_TYPE:
        raise ValueError(
            f"Materials set '{material_set.get('name')}' is '{entity_set_type}', not "
            f"'{ORDERED_ENTITY_SET_TYPE}'. Its members carry no path order."
        )
    return material_set


def list_materials_in_set(api_client: APIClient, owner_id: str, material_set: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Members of an already-resolved set, ascending by `inSet.index`
    (first -> optional intermediates -> last). Takes a resolved set so callers
    that already have one do not re-query for it.
    """
    material_set_id = material_set["_id"]
    matches = api_client.materials.list(
        {"owner._id": owner_id, "inSet._id": material_set_id, "isEntitySet": {"$ne": True}}
    )
    members = [material for material in matches if not material.get("isEntitySet")]
    return sorted(members, key=lambda material: _index_in_set(material, material_set_id))


def list_materials_by_set(
    api_client: APIClient,
    owner_id: str,
    material_set_name: str,
    require_ordered: bool = False,
) -> List[Dict[str, Any]]:
    """Resolve a materials set by name and list its members in path order."""
    material_set = find_material_set(api_client, owner_id, material_set_name, require_ordered=require_ordered)
    return list_materials_in_set(api_client, owner_id, material_set)


def get_or_create_materials_set(
    api_client: APIClient,
    owner_id: str,
    material_set_name: str,
    materials: List[Any],
    is_ordered: bool = False,
) -> Dict[str, Any]:
    """
    Reuse an existing materials set by name, or create one, then move members into it.

    Members are moved one at a time in list order: the platform assigns `inSet.index`
    in the order it receives them, which is what makes an ordered set's path order
    match the caller's list.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID under which to find or create the set.
        material_set_name (str): Name of the set to reuse or create.
        materials (list): Members to include (dict responses or Made objects with `.id`).
        is_ordered (bool): Whether path order (`inSet.index`) matters for this set.

    Returns:
        dict: The existing or newly created materials set document.

    Raises:
        ValueError: If materials are empty, if an ordered set has fewer than two members,
            or if an existing set of that name has the opposite `entitySetType`.
    """
    if not materials:
        raise ValueError("Materials set needs at least one material.")
    if is_ordered and len(materials) < 2:
        raise ValueError("Ordered materials set needs at least two materials.")

    entity_set_type = ORDERED_ENTITY_SET_TYPE if is_ordered else UNORDERED_ENTITY_SET_TYPE
    try:
        materials_set: Optional[Dict[str, Any]] = find_material_set(api_client, owner_id, material_set_name)
    except ValueError:
        materials_set = None

    if materials_set is None:
        materials_set = api_client.materials.create_set(
            {"name": material_set_name, "owner": {"_id": owner_id}, "entitySetType": entity_set_type}
        )
        print(f"✅ Materials set '{materials_set['name']}' ({entity_set_type}, {materials_set['_id']})")
    else:
        existing_type = materials_set.get("entitySetType")
        if existing_type != entity_set_type:
            raise ValueError(
                f"Materials set '{materials_set['name']}' already exists as '{existing_type}', but "
                f"'{entity_set_type}' was requested. Reusing it would silently drop path order."
            )
        print(f"♻️  Reusing materials set '{materials_set['name']}' ({existing_type}, {materials_set['_id']})")

    for material in materials:
        identifier = material["_id"] if isinstance(material, dict) else material.id
        api_client.materials.move_to_set(identifier, "", materials_set["_id"])
    return materials_set
