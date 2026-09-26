"""Formation energies of charged defects: dependence on the Fermi level and on the supercell size.

Pure computation — no API calls, no display. Kept apart from `analysis.py`, which imports pymatgen's
phase diagram module at load time; that module needs tqdm, which JupyterLite does not install.

The Fermi level is the electron chemical potential mu_e, measured from the valence band maximum (VBM).
"""

from typing import Dict, Sequence

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
