from typing import Any, Dict, List


def flatten_scope_track(scope_track: List[dict]) -> Dict[str, Any]:
    """The global scope of a job's `scopeTrack`, later values overriding earlier ones."""
    return {key: value for item in scope_track for key, value in item["scope"]["global"].items()}


def get_formation_energy_at_chemical_potentials(scope: Dict[str, Any], delta_mu: Dict[str, float]) -> float:
    """
    Defect formation energy at the chemical potentials mu_i = E_i + delta_mu[i], from its job's flattened scope.

    E_i is the elemental energy per atom the job used, so the stored value is the one at delta_mu = 0:
    E_f(delta_mu) = E_f - sum_i dN_i * delta_mu[i].

    Raises:
        KeyError: If `delta_mu` has no value for an element of the job, including one with dN_i = 0.
    """
    return scope["DEFECT_FORMATION_ENERGY"] - sum(
        count * delta_mu[element] for element, count in scope["DELTA_N_BY_SYMBOL"].items()
    )
