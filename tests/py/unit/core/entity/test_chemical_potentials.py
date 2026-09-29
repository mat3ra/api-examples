"""Unit tests for chemical potentials from reference materials."""

import pytest
from mat3ra.notebooks_utils.core.entity.property.chemical_potentials import solve_chemical_potentials

# Total energies (eV) as (atom counts, energy) of the Standata materials, PBE; ZrO2 is illustrative.
O2 = ({"O": 8}, -3499.6187)
HF = ({"Hf": 2}, -4320.4730)
ZR = ({"Zr": 2}, -2698.0925)
HFO2 = ({"Hf": 4, "O": 8}, -12183.3350)
HFO2_3X3X3 = ({"Hf": 108, "O": 216}, 27 * -12183.3350)
ZRO2 = ({"Zr": 4, "O": 8}, -9800.0)
MU_O_RICH = -3499.6187 / 8
MU_HF_O_POOR = -4320.4730 / 2


@pytest.mark.parametrize(
    "reference_energies, expected",
    [
        ({"O": O2, "Hf": HF, "Zr": ZR}, {"O": MU_O_RICH, "Hf": MU_HF_O_POOR, "Zr": -2698.0925 / 2}),
        (
            {"O": O2, "Hf": HFO2, "Zr": ZRO2},
            {"O": MU_O_RICH, "Hf": -12183.3350 / 4 - 2 * MU_O_RICH, "Zr": -9800.0 / 4 - 2 * MU_O_RICH},
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
