from typing import List, Optional

from mat3ra.api_client import APIClient, PropertiesEndpoints
from mat3ra.prode import PropertyName

from .job import get_fermi_energy_flowchart_id

FERMI_ENERGY_PROPERTIES = {
    PropertyName.non_scalar.band_structure.value,
    PropertyName.non_scalar.density_of_states.value,
}


def _get_properties_for_job(
    client: APIClient, job_id: str, property_name: Optional[str] = None, unit_id: Optional[str] = None
) -> List[dict]:
    """
    Replacement for the broken `client.properties.get_for_job()`: that method builds its filter
    as `{"source.info.jobId": ..., "data.name": ...}` via `.list()`, which wraps it as a
    query=<json> blob - the properties list endpoint (migrated to a validated use case) silently
    drops it, since it only accepts flat, declared keys. "jobId"/"slug" are the flat equivalents
    of "source.info.jobId"/"data.name"; there's no flat equivalent for "source.info.unitId", so
    that part (rare - only used for disambiguating fermiEnergy by flowchart unit) is filtered in
    Python. Returns each match's "data" sub-dict, matching get_for_job()'s own return shape.
    """
    params = {"jobId": job_id}
    if property_name:
        params["slug"] = property_name
    holders = client.properties.request(
        "GET", client.properties.name, params=params, headers=client.properties.headers
    )
    if unit_id:
        holders = [h for h in holders if h.get("source", {}).get("info", {}).get("unitId") == unit_id]
    return [holder["data"] for holder in holders]


def get_properties_for_job(client: APIClient, job_id: str, property_name: Optional[str] = None) -> List[dict]:
    """
    Fetch properties for a job, automatically enriching band_structure/DOS results with fermiEnergy.
    Use instead of client.properties.get_for_job when passing results to visualize_properties.
    """
    job = client.jobs.get(job_id)
    properties = _get_properties_for_job(client, job_id, property_name)
    if property_name not in FERMI_ENERGY_PROPERTIES:
        return properties
    flowchart_id = get_fermi_energy_flowchart_id(job)
    fermi_energy = None
    if flowchart_id:
        fe_props = _get_properties_for_job(client, job_id, PropertyName.scalar.fermi_energy.value, flowchart_id)
        if fe_props:
            fermi_energy = fe_props[0].get("value")
    return [{**prop, "fermiEnergy": fermi_energy} for prop in properties]


def get_property_holder_for_job(
    client: APIClient, job_id: str, property_name: str, unit_id: Optional[str] = None
) -> dict:
    """
    Fetch the first full property holder for a job/property pair.

    Args:
        client (APIClient): API client instance.
        job_id (str): Job ID.
        property_name (str): Property name.
        unit_id (str, optional): Unit flowchart ID.

    Returns:
        dict: Full property holder document.
    """
    # Using .request() with flat params instead of .list(): see _get_properties_for_job above for
    # why, and note this function (unlike get_properties_for_job) needs the full property holder,
    # not just its "data" sub-dict.
    params = {"jobId": job_id, "slug": property_name}
    holders = client.properties.request(
        "GET", client.properties.name, params=params, headers=client.properties.headers
    )
    if unit_id:
        holders = [h for h in holders if h.get("source", {}).get("info", {}).get("unitId") == unit_id]
    if not holders:
        raise ValueError(f"Property '{property_name}' not found for job '{job_id}'")
    return holders[0]


def update_property_holder_value(client: APIClient, property_holder_id: str, value: float) -> dict:
    """
    Update a scalar property's data.value.

    Args:
        client (APIClient): API client instance.
        property_holder_id (str): Property holder ID.
        value (float): New scalar value.

    Returns:
        dict: Server response payload.
    """
    return client.properties.update(property_holder_id, {"$set": {"data.value": value}})


def find_total_energy_for_material(client: APIClient, material_id: str, source: str = "my_account") -> Optional[dict]:
    """
    Find the best-precision total_energy property for a material. Mirrors the
    platform's "Resolve Total Energies for Elemental Materials" subworkflow,
    which queries properties directly by material and selects by precision --
    no job lookup involved.

    Properties are keyed by the material's `exabyteId`, not its platform `_id`,
    so the material is fetched first to resolve that field.

    Args:
        client (APIClient): API client instance.
        material_id (str): Material _id to look up the total_energy property for.
        source (str): Source of the total energy property: `my_account` (default), `curators` or
            `public`.

    Returns:
        The best-precision total_energy property, or None if none exists.
    """
    material = client.materials.get(material_id)
    exabyte_id = material.get("exabyteId")
    if not exabyte_id:
        return None
    # Using .request() with flat params instead of .list(): see _get_properties_for_job above for
    # why. "owner.slug"/"owner._id" map onto the flat "ownerSlug"/"ownerId" keys; sorting/limiting
    # by best precision has no flat equivalent (the endpoint's "sort" param expects a nested
    # object, which a simple flat query param can't carry), so that's done in Python instead -
    # there are only ever a few differently-precise total_energy properties per material.
    params = {"exabyteId": exabyte_id, "slug": "total_energy"}
    if source == "curators":
        params["ownerSlug"] = "curators"
    elif source == "my_account":
        params["ownerId"] = client.my_account.id
    elif source != "public":
        raise ValueError(f"Invalid source: {source!r}. Expected 'public', 'curators', or 'my_account'.")
    properties = client.properties.request(
        "GET", client.properties.name, params=params, headers=client.properties.headers
    )
    if not properties:
        return None
    return max(properties, key=lambda prop: prop.get("precision", {}).get("value", 0))


def get_property_by_subworkflow_and_unit_indicies(
    endpoint: PropertiesEndpoints, property_name: str, job: dict, subworkflow_index: int, unit_index: int
) -> dict:
    """
    Returns the property extracted in the given unit of the job's subworkflow.

    Args:
        endpoint (PropertiesEndpoints): an instance of PropertiesEndpoints class.
        property_name (str): name of property to extract.
        job (dict): job config to extract the property from.
        subworkflow_index (int): index of subworkflow to extract the property from.
        unit_index (int): index of unit to extract the property from.

    Returns:
        dict: extracted property
    """
    unit_flowchart_id = job["workflow"]["subworkflows"][subworkflow_index]["units"][unit_index]["flowchartId"]
    return endpoint.get_property(job["_id"], unit_flowchart_id, property_name)
