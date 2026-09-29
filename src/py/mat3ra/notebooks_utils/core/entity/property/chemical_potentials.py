from collections import Counter
from typing import Any, Dict, List, Tuple

import numpy as np
from mat3ra.api_client import APIClient
from mat3ra.made.material import Material

from ..job.api import get_kgrid_of_job


def solve_chemical_potentials(reference_energies: Dict[str, Tuple[Dict[str, int], float]]) -> Dict[str, float]:
    """
    Chemical potential of each element (eV/atom) from one reference material per element, given as its atom counts
    and its total energy (eV) for them: each material gives E = sum_i n_i * mu_i, and the square system is solved.

    Raises:
        ValueError: If the materials contain other elements than the keys, or do not determine every potential.
    """
    elements = sorted(reference_energies)
    compositions = [composition for composition, _ in reference_energies.values()]
    if set().union(*compositions) != set(elements):
        raise ValueError(f"The reference materials must contain exactly the elements {elements}.")
    matrix = np.array([[composition.get(element, 0) for element in elements] for composition in compositions])
    if np.linalg.matrix_rank(matrix) < len(elements):
        raise ValueError("The reference materials do not determine every chemical potential.")
    energies = [energy for _, energy in reference_energies.values()]
    return dict(zip(elements, np.linalg.solve(matrix, energies).tolist()))


def get_reference_energies(
    client: APIClient,
    materials_by_element: Dict[str, Material],
    owner_id: str,
    kgrid: List[int],
    host_energy: Dict[str, float],
) -> Dict[str, Tuple[Dict[str, int], float]]:
    """
    Atom counts and total energy of each platform material, as `solve_chemical_potentials` takes them. The energy is
    `host_energy[material.id]` when given there, else that of the material's finished Total Energy job of `owner_id`:
    the one on `kgrid`, else the only one, or one of several on the same other k-grid.

    Raises:
        RuntimeError: If a material has no such job, or has them only on several other k-grids.
    """
    reference_energies = {}
    for element, material in materials_by_element.items():
        if material.id in host_energy:
            energy, source = host_energy[material.id], "pristine reference"
        else:
            query = {"_material._id": material.id, "owner._id": owner_id, "status": "finished"}
            jobs = [job for job in client.jobs.list(query) if client.properties.get_for_job(job["_id"], "total_energy")]
            jobs = [job for job in jobs if get_kgrid_of_job(job) == kgrid] or jobs
            if len({str(get_kgrid_of_job(job)) for job in jobs}) != 1:
                found = ", ".join(f"job {job['_id']} on {get_kgrid_of_job(job)}" for job in jobs) or "none"
                raise RuntimeError(f"Run Total Energy on '{material.name}' at k-grid {kgrid}; found: {found}.")
            energy = client.properties.get_for_job(jobs[0]["_id"], property_name="total_energy")[0]["value"]
            source = f"job {jobs[0]['_id']}, k-grid {get_kgrid_of_job(jobs[0])}"
        print(f"{element}: {material.name}, {source}, E = {energy:.4f} eV")
        reference_energies[element] = (dict(Counter(material.basis.elements.values)), energy)
    return reference_energies


def flatten_scope_track(scope_track: List[dict]) -> Dict[str, Any]:
    """The global scope of a job's `scopeTrack`, later values overriding earlier ones."""
    return {key: value for item in scope_track for key, value in item["scope"]["global"].items()}


def get_formation_energy_at_references(scope: Dict[str, Any], chemical_potentials: Dict[str, float]) -> float:
    """Defect formation energy at `chemical_potentials` from its job's flattened scope, stored at elemental E_i."""
    delta_n_times_mu = sum(
        count * chemical_potentials[element] for element, count in scope["DELTA_N_BY_SYMBOL"].items()
    )
    return scope["DEFECT_FORMATION_ENERGY"] + scope["SUM_DELTA_N_TIMES_MU"] - delta_n_times_mu
