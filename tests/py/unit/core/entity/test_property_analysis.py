"""Unit tests for convex hull (phase stability) analysis."""
from typing import List

from mat3ra.notebooks_utils.core.entity.property.analysis import (
    PhaseStabilityEntry,
    build_convex_hull,
    get_results_table,
)

# Realistic total energies (eV) for the Hf-Zr-O system (PBE-level)
ENTRIES_DATA: List[PhaseStabilityEntry] = [
    {"material_id": "hf", "formula": "Hf", "composition": {"Hf": 2}, "n_atoms": 2, "total_energy": -23.86},
    {"material_id": "zr", "formula": "Zr", "composition": {"Zr": 2}, "n_atoms": 2, "total_energy": -18.56},
    {"material_id": "o2", "formula": "O2", "composition": {"O": 2}, "n_atoms": 2, "total_energy": -9.86},
    {
        "material_id": "hfo2",
        "formula": "HfO2",
        "composition": {"Hf": 4, "O": 8},
        "n_atoms": 12,
        "total_energy": -131.64,
    },
    {
        "material_id": "zro2",
        "formula": "ZrO2",
        "composition": {"Zr": 4, "O": 8},
        "n_atoms": 12,
        "total_energy": -112.74,
    },
]


def test_build_convex_hull():
    phase_diagram = build_convex_hull(ENTRIES_DATA)
    assert phase_diagram is not None
    assert len(phase_diagram.all_entries) == len(ENTRIES_DATA)
    assert len(phase_diagram.elements) == 3  # Hf, Zr, O


def test_get_results_table():
    phase_diagram = build_convex_hull(ENTRIES_DATA)
    df = get_results_table(phase_diagram, ENTRIES_DATA)
    assert len(df) == len(ENTRIES_DATA)
    assert "Formula" in df.columns
    assert "Above hull (eV)" in df.columns
    assert "Stable" in df.columns
    assert "E/atom (eV)" in df.columns
    assert "Eform/atom (eV)" in df.columns


def test_elemental_entries_on_hull():
    phase_diagram = build_convex_hull(ENTRIES_DATA)
    df = get_results_table(phase_diagram, ENTRIES_DATA)
    for element in ["Hf", "Zr"]:
        row = df[df["Formula"] == element]
        assert len(row) == 1
        assert row.iloc[0]["Above hull (eV)"] == 0.0
        assert row.iloc[0]["Stable"] == "✅"


def test_formation_energy_of_elements_is_zero():
    phase_diagram = build_convex_hull(ENTRIES_DATA)
    df = get_results_table(phase_diagram, ENTRIES_DATA)
    for element in ["Hf", "Zr", "O2"]:
        row = df[df["Formula"] == element]
        assert row.iloc[0]["Eform/atom (eV)"] == 0.0


def test_single_element_system():
    entries: List[PhaseStabilityEntry] = [
        {"material_id": "si", "formula": "Si", "composition": {"Si": 2}, "n_atoms": 2, "total_energy": -10.84},
    ]
    phase_diagram = build_convex_hull(entries)
    df = get_results_table(phase_diagram, entries)
    assert len(df) == 1
    assert df.iloc[0]["Formula"] == "Si"
    assert df.iloc[0]["Above hull (eV)"] == 0.0
    assert df.iloc[0]["Stable"] == "✅"
