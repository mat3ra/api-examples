from typing import List, Optional

from mat3ra.api_client import APIClient
from mat3ra.api_client.tools.property import (
    find_total_energy_for_material,
    get_property_by_subworkflow_and_unit_indicies,
    get_property_holder_for_job,
    update_property_holder_value,
)
from mat3ra.prode import PropertyName

from .job import get_fermi_energy_flowchart_id

FERMI_ENERGY_PROPERTIES = {
    PropertyName.non_scalar.band_structure.value,
    PropertyName.non_scalar.density_of_states.value,
}


def get_properties_for_job(client: APIClient, job_id: str, property_name: Optional[str] = None) -> List[dict]:
    """
    Fetch properties for a job, automatically enriching band_structure/DOS results with fermiEnergy.
    Use instead of client.properties.get_for_job when passing results to visualize_properties.
    """
    job = client.jobs.get(job_id)
    properties = client.properties.get_for_job(job_id, property_name)
    if property_name not in FERMI_ENERGY_PROPERTIES:
        return properties
    flowchart_id = get_fermi_energy_flowchart_id(job)
    fermi_energy = None
    if flowchart_id:
        fe_props = client.properties.get_for_job(job_id, PropertyName.scalar.fermi_energy.value, flowchart_id)
        if fe_props:
            fermi_energy = fe_props[0].get("value")
    return [{**prop, "fermiEnergy": fermi_energy} for prop in properties]


__all__ = [
    "FERMI_ENERGY_PROPERTIES",
    "find_total_energy_for_material",
    "get_properties_for_job",
    "get_property_by_subworkflow_and_unit_indicies",
    "get_property_holder_for_job",
    "update_property_holder_value",
]
