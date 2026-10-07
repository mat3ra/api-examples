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
    for entry in phase_diagram.all_entries:
        energy_above_hull = phase_diagram.get_e_above_hull(entry)
        decomposition = phase_diagram.get_decomposition(entry.composition)
        decomposition_str = " + ".join([e.composition.reduced_formula for e in decomposition])
        results.append(
            {
                "Formula": entry.composition.reduced_formula,
                "Material ID": entry.entry_id,
                "E/atom (eV)": round(entry.energy_per_atom, 4),
                "Eform/atom (eV)": round(phase_diagram.get_form_energy_per_atom(entry), 4),
                "Above hull (eV)": round(energy_above_hull, 4),
                "Stable": "✅" if energy_above_hull < 1e-6 else "❌",
                "Decomposes to": decomposition_str if energy_above_hull > 1e-6 else "—",
            }
        )

    return pd.DataFrame(results).sort_values("Above hull (eV)")


def get_chemical_potentials_table(phase_diagram: PhaseDiagram) -> pd.DataFrame:
    """Build a chemical potentials DataFrame from phase diagram analysis.

    Args:
        phase_diagram: pymatgen PhaseDiagram object.

    Returns:
        DataFrame with Δμ per element (eV, relative to the elemental reference)
        at each corner of every stable compound's stability region.
    """
    results = []
    for entry in sorted(phase_diagram.stable_entries, key=lambda entry: entry.composition.reduced_formula):
        if entry.is_element:
            continue
        for facet_name, chemical_potentials in phase_diagram.get_all_chempots(entry.composition).items():
            row = {"Formula": entry.composition.reduced_formula, "Phases in equilibrium": facet_name}
            for element, chemical_potential in chemical_potentials.items():
                row[f"Δμ_{element} (eV)"] = round(
                    chemical_potential - phase_diagram.el_refs[element].energy_per_atom, 4
                )
            results.append(row)

    return pd.DataFrame(results)
