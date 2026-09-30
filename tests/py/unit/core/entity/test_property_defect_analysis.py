"""Unit tests for charged-defect formation energy analysis."""

from unittest.mock import MagicMock

import numpy as np
import pytest
from mat3ra.notebooks_utils.core.entity.property.defect_analysis import (
    FERMI_LEVEL_COLUMN,
    FORMATION_ENERGY_AT_VBM_COLUMN,
    STABLE_FROM_COLUMN,
    STABLE_TO_COLUMN,
    DefectJobResult,
    evaluate_finite_size_fit,
    fit_finite_size,
    get_charge_state_table,
    get_chemical_potential_combination,
    get_defect_job_result,
    get_formation_energies_vs_fermi_level,
    get_formation_energy_at_chemical_potentials,
)

# GaAs As-vacancy formation energies at the VBM (eV), 2x2x2 cell, from the QuantumATK tutorial.
FORMATION_ENERGIES_AT_VBM = {1: 3.04, 0: 3.22, -1: 3.56, -2: 4.23, -3: 5.18}
BAND_GAP = 1.5


def test_get_formation_energies_vs_fermi_level_are_lines_of_slope_charge():
    lines = get_formation_energies_vs_fermi_level(FORMATION_ENERGIES_AT_VBM, BAND_GAP, number_of_points=4)
    assert list(lines.columns) == [-3, -2, -1, 0, 1]
    assert lines.index.name == FERMI_LEVEL_COLUMN
    assert lines.index.tolist() == [0.0, 0.5, 1.0, 1.5]
    assert lines[1].tolist() == pytest.approx([3.04, 3.54, 4.04, 4.54])
    assert lines[-2].tolist() == pytest.approx([4.23, 3.23, 2.23, 1.23])


def test_get_charge_state_table_gives_the_exact_transition_levels():
    # Transition levels: +1/0 at 0.18, 0/-1 at 0.34, -1/-2 at 0.67, -2/-3 at 0.95 eV.
    table = get_charge_state_table(FORMATION_ENERGIES_AT_VBM, BAND_GAP)
    assert table.index.tolist() == [-3, -2, -1, 0, 1]
    assert table[FORMATION_ENERGY_AT_VBM_COLUMN].to_dict() == FORMATION_ENERGIES_AT_VBM
    assert table[STABLE_FROM_COLUMN].to_dict() == pytest.approx({1: 0.0, 0: 0.18, -1: 0.34, -2: 0.67, -3: 0.95})
    assert table[STABLE_TO_COLUMN].to_dict() == pytest.approx({1: 0.18, 0: 0.34, -1: 0.67, -2: 0.95, -3: 1.5})


def test_get_charge_state_table_leaves_the_range_empty_for_a_state_that_is_never_stable():
    table = get_charge_state_table({0: 1.0, 1: 5.0}, band_gap=1.0)
    assert table.loc[0, [STABLE_FROM_COLUMN, STABLE_TO_COLUMN]].tolist() == [0.0, 1.0]
    assert table.loc[1, [STABLE_FROM_COLUMN, STABLE_TO_COLUMN]].isna().all()


def test_fit_finite_size_recovers_the_coefficients():
    lengths = np.array([10.0, 15.0, 20.0])
    fit = fit_finite_size(lengths, 2.0 + 3.0 / lengths)
    assert fit == pytest.approx({"E_inf": 2.0, "a": 3.0})
    assert evaluate_finite_size_fit(fit, [0.0, 0.1]).tolist() == pytest.approx([2.0, 2.3])


def test_fit_finite_size_fits_the_cubic_term_with_four_sizes():
    lengths = np.array([10.0, 15.0, 20.0, 30.0])
    fit = fit_finite_size(lengths, 2.0 + 3.0 / lengths - 500.0 / lengths**3)
    assert fit == pytest.approx({"E_inf": 2.0, "a": 3.0, "b": -500.0})


def test_fit_finite_size_needs_two_sizes():
    with pytest.raises(ValueError, match="at least two"):
        fit_finite_size([10.0], [2.3])


# scopeTrack globals of the m-HfO2 jobs rxCNizLKg7hkrPgAh (Zr_Hf) and mpxeDWYNKPBr6zc8Z (V_O).
HAFNIUM = {"total_energy_per_atom": -2160.2365}
OXYGEN = {"total_energy_per_atom": -437.4523}
ZIRCONIUM = {"total_energy_per_atom": -1349.0462}
ZR_HF_JOB = {
    "scopeTrack": [
        {"scope": {"global": {"DELTA_N_BY_SYMBOL": {"Hf": -1, "O": 0, "Zr": 1}}}},
        {"scope": {"global": {"TE_CONTRIBUTIONS_BY_SYMBOL": {"Hf": HAFNIUM, "O": OXYGEN, "Zr": ZIRCONIUM}}}},
        {"scope": {"global": {"DEFECT_FORMATION_ENERGY": 0.3664}}},
    ]
}
V_O_JOB = {
    "scopeTrack": [
        {"scope": {"global": {"DELTA_N_BY_SYMBOL": {"O": -1, "Hf": 0}}}},
        {"scope": {"global": {"TE_CONTRIBUTIONS_BY_SYMBOL": {"Hf": HAFNIUM, "O": OXYGEN}}}},
        {"scope": {"global": {"DEFECT_FORMATION_ENERGY": 6.356}}},
    ]
}
ZR_HF_RESULT = DefectJobResult(
    0.3664, {"Hf": -1, "O": 0, "Zr": 1}, {"Hf": -2160.2365, "O": -437.4523, "Zr": -1349.0462}
)
V_O_RESULT = DefectJobResult(6.356, {"O": -1, "Hf": 0}, {"Hf": -2160.2365, "O": -437.4523})
ZR_HF_DELTA_MU = {"O": 0.0, "Hf": -10.693, "Zr": -10.340}
V_O_DELTA_MU = {"O": -5.346, "Hf": 0.0}


@pytest.mark.parametrize("job, expected", [(ZR_HF_JOB, ZR_HF_RESULT), (V_O_JOB, V_O_RESULT)])
def test_get_defect_job_result(job, expected):
    api_client = MagicMock()
    api_client.jobs.get.return_value = job
    assert get_defect_job_result(api_client, "job-1") == expected
    api_client.jobs.get.assert_called_once_with("job-1")


@pytest.mark.parametrize(
    "result, delta_mu, expected",
    [
        (ZR_HF_RESULT, {"O": 0.0, "Hf": 0.0, "Zr": 0.0}, 0.3664),
        (ZR_HF_RESULT, ZR_HF_DELTA_MU, 0.0134),
        (V_O_RESULT, V_O_DELTA_MU, 1.010),
        (V_O_RESULT, ZR_HF_DELTA_MU, 6.356),  # Zr is not an element of the job, so its delta_mu is ignored
    ],
)
def test_get_formation_energy_at_chemical_potentials(result, delta_mu, expected):
    assert get_formation_energy_at_chemical_potentials(result, delta_mu) == pytest.approx(expected, abs=1e-4)


def test_get_formation_energy_at_chemical_potentials_raises_on_a_missing_element():
    with pytest.raises(KeyError):
        get_formation_energy_at_chemical_potentials(ZR_HF_RESULT, V_O_DELTA_MU)


@pytest.mark.parametrize(
    "delta_n_by_symbol, expected",
    [({"O": -1, "Hf": 0}, "Δμ_O"), ({"Zr": 1, "Hf": -1, "O": 0}, "Δμ_Hf − Δμ_Zr"), ({"O": -2}, "2Δμ_O")],
)
def test_get_chemical_potential_combination(delta_n_by_symbol, expected):
    assert get_chemical_potential_combination(delta_n_by_symbol) == expected
