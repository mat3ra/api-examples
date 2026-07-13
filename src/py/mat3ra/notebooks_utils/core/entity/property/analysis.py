"""Phase stability (convex hull) analysis using pymatgen.

Pure computation — no API calls, no display.
"""

from typing import Dict, List, TypedDict

import pandas as pd
from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.core import Composition
from pymatgen.entries.computed_entries import ComputedEntry

# TODO: move this to Prode


class PhaseStabilityEntry(TypedDict):
    material_id: str
    formula: str
    composition: Dict[str, int]
    n_atoms: int
    total_energy: float


def build_convex_hull(entries_data: List[PhaseStabilityEntry]) -> PhaseDiagram:
    """Build a pymatgen PhaseDiagram from phase stability entries.

    Args:
        entries_data: List of dicts with composition, total_energy, and optional material_id.

    Returns:
        pymatgen PhaseDiagram object.
    """
    entries = []
    for data in entries_data:
        composition = Composition(data["composition"])
        entry = ComputedEntry(
            composition,
            data["total_energy"],
            entry_id=data.get("material_id", ""),
        )
        entries.append(entry)

    return PhaseDiagram(entries)


def get_results_table(phase_diagram: PhaseDiagram, entries_data: List[PhaseStabilityEntry]) -> pd.DataFrame:
    """Build a results DataFrame from phase diagram analysis.

    Args:
        phase_diagram: pymatgen PhaseDiagram object.
        entries_data: List of PhaseStabilityEntry (same order as build_convex_hull input).

    Returns:
        DataFrame with formula, material ID, energies, stability, and decomposition.
    """
    results = []
    for i, entry in enumerate(phase_diagram.all_entries):
        energy_above_hull = phase_diagram.get_e_above_hull(entry)
        decomposition = phase_diagram.get_decomposition(entry.composition)
        decomposition_str = " + ".join([e.composition.reduced_formula for e in decomposition])
        data = entries_data[i]
        results.append(
            {
                "Formula": entry.composition.reduced_formula,
                "Material ID": data.get("material_id", ""),
                "E/atom (eV)": round(entry.energy_per_atom, 4),
                "Eform/atom (eV)": round(phase_diagram.get_form_energy_per_atom(entry), 4),
                "Above hull (eV)": round(energy_above_hull, 4),
                "Stable": "✅" if energy_above_hull < 1e-6 else "❌",
                "Decomposes to": decomposition_str if energy_above_hull > 1e-6 else "—",
            }
        )

    return pd.DataFrame(results).sort_values("Above hull (eV)")
