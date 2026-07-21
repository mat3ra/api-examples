from typing import Any, Dict, List, Optional


def get_or_create_material(api_client: Any, material, owner_id: str) -> dict:
    """
    Returns an existing material from the collection if one with the same structural hash
    exists under the given owner, otherwise creates a new one.

    Args:
        api_client: API client instance carrying the authorization context.
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


def _exclude_entity_sets(materials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [material for material in materials if not material.get("isEntitySet")]


def _index_in_set(material: Dict[str, Any], material_set_id: str) -> float:
    for entry in material.get("inSet") or []:
        if entry.get("_id") == material_set_id:
            index = entry.get("index")
            return float(index) if index is not None else float("inf")
    return float("inf")


def find_material_set(api_client: Any, owner_id: str, material_set_name: str) -> Dict[str, Any]:
    """
    Find a materials entity set by name (case-insensitive substring match).

    Args:
        api_client: API client instance carrying the authorization context.
        owner_id: Account ID that owns the set.
        material_set_name: Substring matched against set names under the owner.

    Returns:
        The first matching materials set document.

    Raises:
        ValueError: If no set matches the name.
    """
    material_sets = api_client.materials.list(
        {
            "owner._id": owner_id,
            "isEntitySet": True,
            "name": {"$regex": material_set_name, "$options": "i"},
        }
    )
    if not material_sets:
        raise ValueError(f"No material set matching '{material_set_name}'")
    return material_sets[0]


def list_materials_by_set(
    api_client: Any,
    owner_id: str,
    material_set_name: str,
) -> List[Dict[str, Any]]:
    """
    List non-set materials in a materials set, ordered by ascending `inSet.index`.

    Path order is first → optional intermediates → last. Tags and material names
    do not define order.

    Args:
        api_client: API client instance carrying the authorization context.
        owner_id: Account ID that owns the set.
        material_set_name: Name (substring) of the ordered materials set.

    Returns:
        Member materials sorted by path index (missing index sorts last).
    """
    material_set = find_material_set(api_client, owner_id, material_set_name)
    material_set_id = material_set["_id"]
    matches = api_client.materials.list(
        {
            "owner._id": owner_id,
            "inSet._id": material_set_id,
        }
    )
    materials = _exclude_entity_sets(matches)
    return sorted(materials, key=lambda material: _index_in_set(material, material_set_id))


def _resolve_material_identifier(material: Any) -> str:
    if isinstance(material, dict):
        return material["_id"]
    return material.id


def _move_materials_into_set(api_client: Any, material_set_id: str, materials: List[Any]) -> None:
    for material in materials:
        api_client.materials.move_to_set(
            _resolve_material_identifier(material),
            "",
            material_set_id,
        )


ORDERED_ENTITY_SET_TYPE = "ordered"
UNORDERED_ENTITY_SET_TYPE = "unordered"


def _find_existing_materials_set(api_client: Any, owner_id: str, material_set_name: str) -> Optional[Dict[str, Any]]:
    try:
        return find_material_set(api_client, owner_id, material_set_name)
    except ValueError:
        return None


def get_or_create_materials_set(
    api_client: Any,
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
        api_client: API client instance carrying the authorization context.
        owner_id: Account ID under which to find or create the set.
        material_set_name: Name of the set to reuse or create.
        materials: Materials to include (dict responses or Made objects with `.id`).
        is_ordered: Whether path order (`inSet.index`) matters for this set.

    Returns:
        The existing or newly created materials set document.

    Raises:
        ValueError: If materials are empty, or ordered set has fewer than two members.
    """
    if not materials:
        raise ValueError("Materials set needs at least one material.")
    if is_ordered and len(materials) < 2:
        raise ValueError("Ordered materials set needs at least two materials.")

    materials_set = _find_existing_materials_set(api_client, owner_id, material_set_name)
    if materials_set is None:
        entity_set_type = ORDERED_ENTITY_SET_TYPE if is_ordered else UNORDERED_ENTITY_SET_TYPE
        set_config = {
            "name": material_set_name,
            "owner": {"_id": owner_id},
            "entitySetType": entity_set_type,
        }
        materials_set = api_client.materials.create_set(set_config)
        print(f"✅ Materials set '{materials_set['name']}' " f"({entity_set_type}, {materials_set['_id']})")
    else:
        print(
            f"♻️  Reusing existing materials set '{materials_set['name']}' "
            f"({materials_set.get('entitySetType')}, {materials_set['_id']})"
        )

    _move_materials_into_set(api_client, materials_set["_id"], materials)
    return materials_set
