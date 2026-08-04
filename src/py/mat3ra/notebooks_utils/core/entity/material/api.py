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
    matches = api_client.materials.list(query)
    material_response = next((item for item in matches if item.get("owner", {}).get("_id") == owner_id), None)
    if material_response is None:
        raise ValueError(
            "The bulk material resolved from metadata is not present on the platform for this account. "
            "Run the Total Energy notebook for that bulk material first, then rerun this notebook."
        )
    return Material.create(material_response)


def _exclude_entity_sets(materials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Drops the set document itself, which the platform returns alongside its members.

    Args:
        materials (list[dict]): Documents returned by a materials list query.

    Returns:
        list[dict]: Only the non-set materials.
    """
    return [material for material in materials if not material.get("isEntitySet")]


def _index_in_set(material: Dict[str, Any], material_set_id: str) -> float:
    """
    Position of a material within a set, used as the path-order sort key.

    A member with no recorded index sorts last rather than first, so a partially
    indexed set degrades to "known order first" instead of silently reshuffling.

    Args:
        material (dict): Material document carrying an `inSet` list.
        material_set_id (str): ID of the set whose index to read.

    Returns:
        float: The `inSet.index` value, or infinity when the set records none.
    """
    for entry in material.get("inSet") or []:
        if entry.get("_id") == material_set_id:
            index = entry.get("index")
            return float(index) if index is not None else float("inf")
    return float("inf")


def _require_ordered(material_set: Dict[str, Any]) -> None:
    """
    Rejects a set whose members carry no path order.

    Only an `ordered` set gets `inSet.index` values assigned. Sorting an unordered
    set by index leaves every member tied, so its order would be whatever the API
    happened to return — a NEB path nobody chose, submitted without an error.

    Args:
        material_set (dict): The resolved materials set document.

    Raises:
        ValueError: If the set is not of the `ordered` entity set type.
    """
    entity_set_type = material_set.get("entitySetType")
    if entity_set_type != ORDERED_ENTITY_SET_TYPE:
        raise ValueError(
            f"Materials set '{material_set.get('name')}' is '{entity_set_type}', not "
            f"'{ORDERED_ENTITY_SET_TYPE}'. Its members carry no path order — change the set "
            f"type on the platform, or build the path with an ordered set."
        )


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
        require_ordered (bool): Reject the match unless it is an ordered set.

    Returns:
        dict: The first matching materials set document.

    Raises:
        ValueError: If no set matches the name, or if `require_ordered` and the match
            is not an ordered set.
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
    if require_ordered:
        _require_ordered(material_set)
    return material_set


def list_materials_in_set(api_client: APIClient, owner_id: str, material_set: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    List non-set members of an already-resolved materials set, ordered by ascending `inSet.index`.

    Path order is first -> optional intermediates -> last. Tags and material names
    do not define order.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID that owns the set.
        material_set (dict): Set document, as returned by `find_material_set`.

    Returns:
        list[dict]: Member materials sorted by path index (missing index sorts last).
    """
    material_set_id = material_set["_id"]
    matches = api_client.materials.list(
        {
            "owner._id": owner_id,
            "inSet._id": material_set_id,
        }
    )
    materials = _exclude_entity_sets(matches)
    return sorted(materials, key=lambda material: _index_in_set(material, material_set_id))


def list_materials_by_set(
    api_client: APIClient,
    owner_id: str,
    material_set_name: str,
    require_ordered: bool = False,
) -> List[Dict[str, Any]]:
    """
    Resolve a materials set by name and list its members in path order.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID that owns the set.
        material_set_name (str): Name (substring) of the materials set.
        require_ordered (bool): Reject the set unless it carries path order.

    Returns:
        list[dict]: Member materials sorted by path index (missing index sorts last).
    """
    material_set = find_material_set(api_client, owner_id, material_set_name, require_ordered=require_ordered)
    return list_materials_in_set(api_client, owner_id, material_set)


def _resolve_material_identifier(material: Any) -> str:
    """
    Reads the platform ID from either an API response dict or a Made material object.

    Args:
        material (dict | Material): Material to identify.

    Returns:
        str: The platform material ID.
    """
    if isinstance(material, dict):
        return material["_id"]
    return material.id


def _move_materials_into_set(api_client: APIClient, material_set_id: str, materials: List[Any]) -> None:
    """
    Moves materials into a set one at a time, in list order.

    Sequential moves are required, not incidental: the platform assigns
    `inSet.index` in the order it receives them, so this loop is what makes an
    ordered set's path order match the caller's list.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        material_set_id (str): ID of the destination set.
        materials (list): Materials to move (dict responses or Made objects with `.id`).
    """
    for material in materials:
        api_client.materials.move_to_set(
            _resolve_material_identifier(material),
            "",
            material_set_id,
        )


def get_or_create_materials_set(
    api_client: APIClient,
    owner_id: str,
    material_set_name: str,
    materials: List[Any],
    is_ordered: bool = False,
) -> Dict[str, Any]:
    """
    Reuse an existing materials set by name, or create one, then move members into it.

    For `is_ordered=True`, members are moved in list order so the platform can
    assign ascending `inSet.index` values (e.g. NEB path). For unordered sets,
    membership is a bag (e.g. convex hull, EOS series).

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        owner_id (str): Account ID under which to find or create the set.
        material_set_name (str): Name of the set to reuse or create.
        materials (list): Materials to include (dict responses or Made objects with `.id`).
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
        set_config = {
            "name": material_set_name,
            "owner": {"_id": owner_id},
            "entitySetType": entity_set_type,
        }
        materials_set = api_client.materials.create_set(set_config)
        print(f"✅ Materials set '{materials_set['name']}' " f"({entity_set_type}, {materials_set['_id']})")
    else:
        existing_entity_set_type = materials_set.get("entitySetType")
        if existing_entity_set_type != entity_set_type:
            raise ValueError(
                f"Materials set '{materials_set['name']}' already exists as "
                f"'{existing_entity_set_type}', but '{entity_set_type}' was requested. "
                f"Reusing it would silently drop path order — rename the set or fix its type."
            )
        print(
            f"♻️  Reusing existing materials set '{materials_set['name']}' "
            f"({existing_entity_set_type}, {materials_set['_id']})"
        )

    _move_materials_into_set(api_client, materials_set["_id"], materials)
    return materials_set
