"""Formation energies of charged defects: dependence on the Fermi level, on the supercell size and on the chemical
potentials.

No display. Kept apart from `analysis.py`, which imports pymatgen's
phase diagram module at load time; that module needs tqdm, which JupyterLite does not install.

The Fermi level is the electron chemical potential mu_e, measured from the valence band maximum (VBM).
"""

from typing import Any, Dict, List, NamedTuple, Sequence

import numpy as np
import pandas as pd

# TODO: move this to Prode

FERMI_LEVEL_COLUMN = "fermi_level"
FORMATION_ENERGY_AT_VBM_COLUMN = "E_f at VBM (eV)"
STABLE_FROM_COLUMN = "Stable from (eV)"
STABLE_TO_COLUMN = "Stable to (eV)"
FINITE_SIZE_FIT_COEFFICIENTS = ("E_inf", "a", "b")


def get_formation_energies_vs_fermi_level(
    formation_energies_at_vbm: Dict[int, float], band_gap: float, number_of_points: int = 201
) -> pd.DataFrame:
    """Formation energy of each charge state as a function of the Fermi level.

    E_f(q, mu_e) = E_f(q, VBM) + q * mu_e, a straight line of slope q, for mu_e from the VBM (0)
    to the conduction band minimum (band_gap).

    Args:
        formation_energies_at_vbm: Formation energy at the VBM (eV), keyed by charge state.
        band_gap: Band gap of the pristine cell (eV), the range of the Fermi level.
        number_of_points: Number of Fermi level values.

    Returns:
        DataFrame indexed by the Fermi level (eV) with one column per charge state, in ascending charge order.
    """
    fermi_levels = np.linspace(0, band_gap, number_of_points)
    lines = {
        charge: formation_energies_at_vbm[charge] + charge * fermi_levels
        for charge in sorted(formation_energies_at_vbm)
    }
    return pd.DataFrame(lines, index=pd.Index(fermi_levels, name=FERMI_LEVEL_COLUMN))


def get_charge_state_table(formation_energies_at_vbm: Dict[int, float], band_gap: float) -> pd.DataFrame:
    """Formation energy at the VBM of each charge state, and the Fermi level range in which it is the stable one.

    A state q is stable where its line lies below every other; against a state q' the two lines cross at
    the transition level (E_f(q') - E_f(q)) / (q - q'), computed exactly rather than on a grid.

    Args:
        formation_energies_at_vbm: Formation energy at the VBM (eV), keyed by charge state.
        band_gap: Band gap of the pristine cell (eV), the range of the Fermi level.

    Returns:
        DataFrame indexed by charge state, in ascending order; the range is NaN for a state that is never stable.
    """
    rows = []
    for charge, energy in sorted(formation_energies_at_vbm.items()):
        lowest, highest = 0.0, band_gap
        for other_charge, other_energy in formation_energies_at_vbm.items():
            if other_charge == charge:
                continue
            transition_level = (other_energy - energy) / (charge - other_charge)
            if charge > other_charge:
                highest = min(highest, transition_level)
            else:
                lowest = max(lowest, transition_level)
        is_stable = lowest <= highest
        rows.append(
            {
                "charge": charge,
                FORMATION_ENERGY_AT_VBM_COLUMN: energy,
                STABLE_FROM_COLUMN: lowest if is_stable else np.nan,
                STABLE_TO_COLUMN: highest if is_stable else np.nan,
            }
        )
    return pd.DataFrame(rows).set_index("charge")


def fit_finite_size(lengths: Sequence[float], energies: Sequence[float]) -> Dict[str, float]:
    """Extrapolates an energy computed at several supercell sizes to the infinite cell.

    Fits E(L) = E_inf + a / L + b / L^3 by least squares, with L the cell length (V^(1/3)); the
    b term, which needs four or more sizes to be a fit rather than an interpolation, is only
    included then.

    Args:
        lengths: Supercell lengths (Angstrom), two or more.
        energies: The energy at each length (eV).

    Returns:
        The coefficients "E_inf" and "a", and "b" when it was fitted.
    """
    lengths_array, energies_array = np.asarray(lengths, dtype=float), np.asarray(energies, dtype=float)
    if len(lengths_array) < 2:
        raise ValueError("The finite-size fit needs at least two supercell sizes.")
    terms = [np.ones_like(lengths_array), 1 / lengths_array]
    if len(lengths_array) > 3:
        terms.append(1 / lengths_array**3)
    coefficients, *_ = np.linalg.lstsq(np.stack(terms, axis=1), energies_array, rcond=None)
    return dict(zip(FINITE_SIZE_FIT_COEFFICIENTS, coefficients.tolist()))


def evaluate_finite_size_fit(fit: Dict[str, float], inverse_lengths: Sequence[float]) -> np.ndarray:
    """E_inf + a / L + b / L^3 from the coefficients of `fit_finite_size`, at the given 1 / L."""
    inverse_lengths_array = np.asarray(inverse_lengths, dtype=float)
    return fit["E_inf"] + fit["a"] * inverse_lengths_array + fit.get("b", 0.0) * inverse_lengths_array**3


class DefectJobResult(NamedTuple):
    formation_energy: float
    delta_n_by_symbol: Dict[str, int]
    reference_energies_per_atom: Dict[str, float]


def _flatten_scope_track(scope_track: List[dict]) -> Dict[str, Any]:
    """The global scope of a job's `scopeTrack`, later values overriding earlier ones."""
    return {key: value for item in scope_track for key, value in item["scope"]["global"].items()}


def get_defect_job_result(api_client, job_id: str) -> DefectJobResult:
    """The result of a finished Defect Formation Energy job, read from its scope."""
    scope = _flatten_scope_track(api_client.jobs.get(job_id)["scopeTrack"])
    return DefectJobResult(
        formation_energy=scope["DEFECT_FORMATION_ENERGY"],
        delta_n_by_symbol=scope["DELTA_N_BY_SYMBOL"],
        reference_energies_per_atom={
            element: contribution["total_energy_per_atom"]
            for element, contribution in scope["TE_CONTRIBUTIONS_BY_SYMBOL"].items()
        },
    )


def get_formation_energy_at_chemical_potentials(result: DefectJobResult, delta_mu: Dict[str, float]) -> float:
    """
    Defect formation energy at the chemical potentials mu_i = E_i + delta_mu[i].

    E_i is the elemental energy per atom the job used, so the stored value is the one at delta_mu = 0:
    E_f(delta_mu) = E_f - sum_i dN_i * delta_mu[i].

    Raises:
        KeyError: If `delta_mu` has no value for an element of the job, including one with dN_i = 0.
    """
    return result.formation_energy - sum(
        count * delta_mu[element] for element, count in result.delta_n_by_symbol.items()
    )


def get_chemical_potential_combination(delta_n_by_symbol: Dict[str, int]) -> str:
    """-sum_i dN_i * delta_mu_i written out, removed atoms first: "Δμ_Hf − Δμ_Zr" for dN = {Hf: -1, Zr: +1}."""
    terms = [
        f"{'+' if count < 0 else '−'} {abs(count) if abs(count) != 1 else ''}Δμ_{element}"
        for element, count in sorted(delta_n_by_symbol.items(), key=lambda item: item[1])
        if count
    ]
    return " ".join(terms).lstrip("+ ")
