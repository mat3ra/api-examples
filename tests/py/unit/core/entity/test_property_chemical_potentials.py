"""Unit tests for chemical potentials from reference materials."""

import pytest
from mat3ra.notebooks_utils.core.entity.property.chemical_potentials import (
    flatten_scope_track,
    get_formation_energy_at_references,
    solve_chemical_potentials,
)

# Total energies (eV) as (atom counts, energy) of the Standata materials, PBE.
O2 = ({"O": 8}, -3499.6187)
HF = ({"Hf": 2}, -4320.4730)
ZR = ({"Zr": 2}, -2698.0925)
HFO2 = ({"Hf": 4, "O": 8}, -12183.3350)
HFO2_3X3X3 = ({"Hf": 108, "O": 216}, 27 * -12183.3350)
ZRO2 = ({"Zr": 4, "O": 8}, -8937.1617)
MU_O_RICH = -3499.6187 / 8
MU_HF_O_POOR = -4320.4730 / 2


@pytest.mark.parametrize(
    "reference_energies, expected",
    [
        ({"O": O2, "Hf": HF, "Zr": ZR}, {"O": MU_O_RICH, "Hf": MU_HF_O_POOR, "Zr": -2698.0925 / 2}),
        (
            {"O": O2, "Hf": HFO2, "Zr": ZRO2},
            {"O": MU_O_RICH, "Hf": -12183.3350 / 4 - 2 * MU_O_RICH, "Zr": -8937.1617 / 4 - 2 * MU_O_RICH},
        ),
        ({"Hf": HF, "O": HFO2}, {"Hf": MU_HF_O_POOR, "O": (-12183.3350 / 4 - MU_HF_O_POOR) / 2}),
    ],
)
def test_solve_chemical_potentials(reference_energies, expected):
    assert solve_chemical_potentials(reference_energies) == pytest.approx(expected)


@pytest.mark.parametrize("reference_energies", [{"Hf": HFO2, "O": HFO2}, {"Hf": HFO2, "O": HFO2_3X3X3}, {"Hf": HFO2}])
def test_solve_chemical_potentials_raises(reference_energies):
    with pytest.raises(ValueError):
        solve_chemical_potentials(reference_energies)


# scopeTrack globals of the m-HfO2 jobs rxCNizLKg7hkrPgAh (Zr_Hf) and mpxeDWYNKPBr6zc8Z (V_O, E_O from O2).
ZR_HF_SCOPE_TRACK = [
    {"scope": {"global": {"SUM_DELTA_N_TIMES_MU": 0.0, "DELTA_N_BY_SYMBOL": {"Hf": -1, "O": 0, "Zr": 1}}}},
    {"scope": {"global": {"SUM_DELTA_N_TIMES_MU": 811.1902858605226, "DEFECT_FORMATION_ENERGY": 0.3664}}},
]
V_O_SCOPE_TRACK = [
    {"scope": {"global": {"DELTA_N_BY_SYMBOL": {"Hf": 0, "O": -1}, "SUM_DELTA_N_TIMES_MU": -MU_O_RICH}}},
    {"scope": {"global": {"DEFECT_FORMATION_ENERGY": 6.356}}},
]


@pytest.mark.parametrize(
    "scope_track, reference_energies, expected",
    [(ZR_HF_SCOPE_TRACK, {"O": O2, "Hf": HFO2, "Zr": ZRO2}, 0.0134), (V_O_SCOPE_TRACK, {"O": O2, "Hf": HFO2}, 6.356)],
)
def test_get_formation_energy_at_references(scope_track, reference_energies, expected):
    chemical_potentials = solve_chemical_potentials(reference_energies)
    scope = flatten_scope_track(scope_track)
    assert get_formation_energy_at_references(scope, chemical_potentials) == pytest.approx(expected, abs=1e-3)
