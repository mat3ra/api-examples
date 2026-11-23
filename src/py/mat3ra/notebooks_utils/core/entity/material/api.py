import os
import re
from typing import Dict, List, Optional

from mat3ra.api_client import APIClient
from mat3ra.api_client.tools.material import (
    ORDERED_ENTITY_SET_TYPE,
    UNORDERED_ENTITY_SET_TYPE,
    find_material_set,
    get_or_create_materials_set,
    list_materials_by_set,
    list_materials_in_set,
)
from mat3ra.made.material import Material
from mat3ra.made.tools.build_components import MaterialWithBuildMetadata
from mat3ra.prode import PropertyName
from mat3ra.standata.materials import Materials

from ..job.api import get_kgrid_query
from ..property.api import get_properties_for_job
from .analysis import get_slab_bulk_crystal, resolve_bulk_query_from_crystal
from .io import load_materials_from_folder


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


def select_material_by_name(materials: List[Material], name: str) -> Material:
    """
    Picks one material by name. An exact name wins; otherwise the name, matched case-insensitively
    as a part of material names, must match exactly one. Materials sharing a name count once: the
    first of them is returned.

    Args:
        materials (List[Material]): Materials to choose from.
        name (str): Exact name, or a part of the name that only one material has.

    Returns:
        Material: The matching material.

    Raises:
        ValueError: If no material matches, or a partial name matches several materials.
    """
    matches: Dict[str, Material] = {}
    for material in materials:
        if name.lower() in material.name.lower():
            matches.setdefault(material.name, material)
    if name in matches:
        return matches[name]
    if len(matches) == 1:
        return next(iter(matches.values()))
    if not matches:
        raise ValueError(f"No material named '{name}'")
    names = "; ".join(f"'{match}'" for match in matches)
    raise ValueError(f"'{name}' matches {len(matches)} materials: {names}. Use a longer or the exact name.")


def load_material(api_client: APIClient, folder: str, name: str, owner_id: str) -> Material:
    """
    Loads a material by name from a folder or the owner's platform collection, chosen as in
    `select_material_by_name`; from Standata when neither has a match.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        folder (str): Folder to look in first, if it exists.
        name (str): Exact name, or a part of the name that only one material has.
        owner_id (str): Account ID whose platform materials are searched.

    Returns:
        Material: The matching material.

    Raises:
        ValueError: If no material matches, or a partial name matches several materials.
    """
    candidates = load_materials_from_folder(folder, verbose=False) if os.path.isdir(folder) else []
    query = {"name": {"$regex": re.escape(name), "$options": "i"}, "owner._id": owner_id}
    candidates += [
        MaterialWithBuildMetadata.create(data)
        for data in api_client.materials.list(query)
        if MaterialWithBuildMetadata.is_valid(data)
    ]
    if not any(name.lower() in candidate.name.lower() for candidate in candidates):
        return Material.create(Materials.get_by_name_first_match(name))
    return select_material_by_name(candidates, name)


def get_final_structure_for_job(api_client: APIClient, job_id: str) -> Material:
    """Fetch the relaxed structure a job reported as its `final_structure` property."""
    properties = get_properties_for_job(api_client, job_id, PropertyName.non_scalar.final_structure.value)
    if not properties:
        raise RuntimeError(f"Job {job_id} reported no 'final_structure'")
    return Material.create(api_client.materials.get(properties[-1]["materialId"]))


def find_relaxed_material(
    api_client: APIClient, material, owner_id: str, kgrid: Optional[List[int]] = None, unit_name: str = "pw_scf"
) -> Optional[Material]:
    """
    Finds a relaxed version of a material: the final structure of a finished job on a material
    with the same structural hash, where the geometry has changed, optionally among the jobs whose
    `unit_name` unit ran on `kgrid`.

    Args:
        api_client (APIClient): API client instance carrying the authorization context.
        material: mat3ra-made Material object (must have a .hash property).
        owner_id (str): Account ID under which to search.
        kgrid (List[int], optional): Exact k-grid dimensions the relaxation ran on; None for no condition.
        unit_name (str): Name of the relaxation unit, e.g. "pw_vc-relax".

    Returns:
        Material, optional: The relaxed structure, or None if none exists.
    """
    ids = [m["_id"] for m in api_client.materials.list({"hash": material.hash, "owner._id": owner_id})]
    query = {"_material._id": {"$in": ids}, "owner._id": owner_id, "status": "finished"}
    for job in api_client.jobs.list({**query, **get_kgrid_query(kgrid, unit_name)}):
        properties = api_client.properties.get_for_job(job["_id"], PropertyName.non_scalar.final_structure.value)
        if not properties:
            continue
        relaxed = api_client.materials.get(properties[-1]["materialId"])
        if relaxed["hash"] != material.hash:
            return Material.create(relaxed)
    return None


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
    matches = api_client.materials.list({**query, "owner._id": owner_id})
    material_response = next(iter(matches), None)
    if material_response is None:
        raise ValueError(
            "The bulk material resolved from metadata is not present on the platform for this account. "
            "Run the Total Energy notebook for that bulk material first, then rerun this notebook."
        )
    return Material.create(material_response)


__all__ = [
    "ORDERED_ENTITY_SET_TYPE",
    "UNORDERED_ENTITY_SET_TYPE",
    "find_material_set",
    "find_relaxed_material",
    "get_bulk_material",
    "get_bulk_material_by_crystal",
    "get_final_structure_for_job",
    "get_or_create_material",
    "get_or_create_materials_set",
    "list_materials_by_set",
    "list_materials_in_set",
    "load_material",
    "select_material_by_name",
]
