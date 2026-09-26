"""Charts for charged-defect formation energies in notebooks.

Kept apart from `plot.py`, which imports pymatgen's phase diagram module at load time; that module
needs tqdm, which JupyterLite does not install.
"""

from typing import Dict

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ....core.entity.property.defect_analysis import evaluate_finite_size_fit

# TODO: move this to Prove

STABLE_STATE_LINE = {"width": 8, "color": "black"}
STABLE_STATE_OPACITY = 0.2
FIT_CURVE_POINTS = 50


def plot_formation_energies_vs_fermi_level(formation_energies: pd.DataFrame, title: str = "") -> go.Figure:
    """One line per charge state over the Fermi level; the lower envelope is the stable state.

    Args:
        formation_energies: Output of `get_formation_energies_vs_fermi_level`.
        title: Figure title.
    """
    fermi_levels = formation_energies.index
    figure = go.Figure()
    for charge in formation_energies.columns:
        figure.add_scatter(x=fermi_levels, y=formation_energies[charge], mode="lines", name=f"q = {charge:+d}")
    figure.add_scatter(
        x=fermi_levels,
        y=formation_energies.min(axis=1),
        mode="lines",
        name="stable state",
        line=STABLE_STATE_LINE,
        opacity=STABLE_STATE_OPACITY,
    )
    figure.update_layout(
        title=title,
        xaxis_title="Fermi level above the VBM (eV)",
        yaxis_title="Formation energy (eV)",
    )
    return figure


def plot_finite_size_fits(results: pd.DataFrame, fits: Dict[int, Dict[str, float]], title: str = "") -> go.Figure:
    """Formation energy against 1 / L per charge state, with each state's `fit_finite_size` curve to 1 / L = 0.

    Args:
        results: One row per calculation with columns "charge", "length" (Angstrom) and "formation_energy" (eV).
        fits: `fit_finite_size` coefficients keyed by charge state; states without one are drawn as points only.
        title: Figure title.
    """
    figure = go.Figure()
    for charge, group in results.groupby("charge"):
        inverse_lengths = 1 / group["length"].to_numpy()
        figure.add_scatter(x=inverse_lengths, y=group["formation_energy"], mode="markers", name=f"q = {charge:+d}")
        if charge in fits:
            curve = np.linspace(0, inverse_lengths.max(), FIT_CURVE_POINTS)
            figure.add_scatter(x=curve, y=evaluate_finite_size_fit(fits[charge], curve), mode="lines", showlegend=False)
    figure.update_layout(
        title=title,
        xaxis_title="1 / L (1/Angstrom), L = V^(1/3)",
        yaxis_title="Formation energy at the VBM (eV)",
    )
    return figure
