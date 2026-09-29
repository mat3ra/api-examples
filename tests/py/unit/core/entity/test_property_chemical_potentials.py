"""Unit tests for defect formation energies at chemical potentials relative to the elemental references."""

import pytest
from mat3ra.notebooks_utils.core.entity.property.chemical_potentials import (
    flatten_scope_track,
    get_formation_energy_at_chemical_potentials,
)

# scopeTrack globals of the m-HfO2 jobs rxCNizLKg7hkrPgAh (Zr_Hf) and mpxeDWYNKPBr6zc8Z (V_O).
ZR_HF_SCOPE_TRACK = [
    {"scope": {"global": {"DELTA_N_BY_SYMBOL": {"Hf": -1, "O": 0, "Zr": 1}}}},
    {"scope": {"global": {"DEFECT_FORMATION_ENERGY": 0.3664}}},
]
V_O_SCOPE_TRACK = [
    {"scope": {"global": {"DELTA_N_BY_SYMBOL": {"O": -1, "Hf": 0}}}},
    {"scope": {"global": {"DEFECT_FORMATION_ENERGY": 6.356}}},
]
ELEMENTAL = {"O": 0.0, "Hf": 0.0, "Zr": 0.0}
O_RICH = {"O": 0.0, "Hf": -10.6926, "Zr": -10.3396}
O_POOR = {"O": -5.346, "Hf": 0.0}


@pytest.mark.parametrize(
    "scope_track, delta_mu, expected",
    [(ZR_HF_SCOPE_TRACK, ELEMENTAL, 0.3664), (ZR_HF_SCOPE_TRACK, O_RICH, 0.0134), (V_O_SCOPE_TRACK, O_POOR, 1.010)],
)
def test_get_formation_energy_at_chemical_potentials(scope_track, delta_mu, expected):
    scope = flatten_scope_track(scope_track)
    assert get_formation_energy_at_chemical_potentials(scope, delta_mu) == pytest.approx(expected, abs=1e-4)


def test_get_formation_energy_at_chemical_potentials_raises_on_a_missing_element():
    with pytest.raises(KeyError):
        get_formation_energy_at_chemical_potentials(flatten_scope_track(ZR_HF_SCOPE_TRACK), O_POOR)
