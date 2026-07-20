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


def _index_in_set(material: Dict[str, Any], set_id: str) -> float:
    for entry in material.get("inSet") or []:
        if entry.get("_id") == set_id:
            index = entry.get("index")
            return float(index) if index is not None else float("inf")
    return float("inf")


def find_material_set(api_client: Any, owner_id: str, material_set_name: str) -> Dict[str, Any]:
    """
    Find a materials entity set by name (case-insensitive substring match).
    """
    sets = api_client.materials.list(
        {
            "owner._id": owner_id,
            "isEntitySet": True,
            "name": {"$regex": material_set_name, "$options": "i"},
        }
    )
    if not sets:
        raise ValueError(f"No material set matching '{material_set_name}'")
    return sets[0]


def list_materials_by_set(
    api_client: Any,
    owner_id: str,
    material_set_name: str,
) -> List[Dict[str, Any]]:
    """
    List non-set materials in a materials set, ordered by inSet index (ascending).

    Matches platform NEB / ordered-set behavior: first, optional intermediates, last.
    """
    material_set = find_material_set(api_client, owner_id, material_set_name)
    set_id = material_set["_id"]
    matches = api_client.materials.list(
        {
            "owner._id": owner_id,
            "inSet._id": set_id,
        }
    )
    materials = _exclude_entity_sets(matches)
    return sorted(materials, key=lambda material: _index_in_set(material, set_id))
