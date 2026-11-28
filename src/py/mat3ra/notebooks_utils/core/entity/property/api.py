from typing import List, Optional

from mat3ra.api_client import APIClient
from mat3ra.api_client.tools.property import find_total_energy_for_material
from mat3ra.api_client.tools.property import get_properties_for_job as _get_properties_for_job
from mat3ra.api_client.tools.property import (
    get_property_by_subworkflow_and_unit_indicies,
    get_property_holder_for_job,
    update_property_holder_value,
)
from mat3ra.prode import FERMI_ENERGY_PROPERTIES, PropertyName, add_fermi_energy_to_properties

from .job import get_fermi_energy_flowchart_id


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
    fermi_energy_properties: List[dict] = []
    if flowchart_id:
        fermi_energy_properties = client.properties.get_for_job(
            job_id, PropertyName.scalar.fermi_energy.value, flowchart_id
        )
    return add_fermi_energy_to_properties(properties, fermi_energy_properties)


__all__ = [
    "FERMI_ENERGY_PROPERTIES",
    "find_total_energy_for_material",
    "get_fermi_energy_flowchart_id",
    "get_properties_for_job",
    "get_property_by_subworkflow_and_unit_indicies",
    "get_property_holder_for_job",
    "update_property_holder_value",
]
