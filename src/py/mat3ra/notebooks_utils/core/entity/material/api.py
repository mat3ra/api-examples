from typing import Any, Dict, List


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


def create_ordered_materials_set(
    api_client: Any,
    owner_id: str,
    material_set_name: str,
    materials: List[Any],
) -> Dict[str, Any]:
    """
    Create an ordered materials set and move members in path order.

    Move order is first → intermediates → last so the platform can assign
    ascending `inSet.index` values that `list_materials_by_set` reads.

    Args:
        api_client: API client instance carrying the authorization context.
        owner_id: Account ID under which to create the set.
        material_set_name: Name for the new ordered set.
        materials: At least two materials (dict responses or Made objects with `.id`).

    Returns:
        The created materials set document.

    Raises:
        ValueError: If fewer than two materials are provided.
    """
    if len(materials) < 2:
        raise ValueError("Ordered NEB set needs at least first and last materials.")
    set_config = {
        "name": material_set_name,
        "owner": {"_id": owner_id},
        "entitySetType": "ordered",
    }
    materials_set = api_client.materials.create_set(set_config)
    _move_materials_into_set(api_client, materials_set["_id"], materials)
    print(f"✅ Ordered materials set '{materials_set['name']}' ({materials_set['_id']})")
    return materials_set
