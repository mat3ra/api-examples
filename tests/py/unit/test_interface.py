import pytest
from mat3ra.notebooks_utils.interface import buckling_text, registry_cell


@pytest.mark.parametrize(
    "buckling,expected",
    [
        (None, "   —   "),
        (0.003, "+0.003"),
        (-0.012, "-0.012"),
    ],
)
def test_buckling_text(buckling, expected):
    assert buckling_text(buckling) == expected


@pytest.mark.parametrize(
    "label,result,expected",
    [
        ("atop_fcc", {"drifted": False, "sites": {"atop", "fcc"}}, "atop_fcc"),
        ("atop_hcp", {"drifted": True, "sites": {None, "atop"}}, "atop_hcp→None/atop"),
        ("hollow", {"drifted": True, "sites": {"fcc", "hcp"}}, "hollow→fcc/hcp"),
    ],
)
def test_registry_cell(label, result, expected):
    assert registry_cell(label, result) == expected
