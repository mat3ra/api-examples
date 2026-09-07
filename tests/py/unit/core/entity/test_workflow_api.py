import pytest
from mat3ra.notebooks_utils.core.entity.workflow.api import set_execution_unit_input


def _unit():
    return {
        "name": "custom_script",
        "input": [
            {"template": {"name": "script.py", "content": "original"}},
            {"template": {"name": "requirements.txt", "content": ""}},
        ],
    }


def test_replaces_the_named_input_and_marks_it_manually_changed():
    """isManuallyChanged is what stops the platform re-rendering the runner's placeholders."""
    unit = _unit()
    set_execution_unit_input(unit, "requirements.txt", "numpy<2\n")

    changed = unit["input"][1]
    assert changed["template"]["content"] == "numpy<2\n"
    assert changed["rendered"] == "numpy<2\n"
    assert changed["isManuallyChanged"] is True
    assert unit["input"][0]["template"]["content"] == "original", "other inputs are untouched"


def test_matches_by_name_not_position():
    """A flavor may list its inputs in any order; position would write into the wrong file."""
    unit = _unit()
    unit["input"].reverse()
    set_execution_unit_input(unit, "script.py", "print(1)")

    by_name = {item["template"]["name"]: item for item in unit["input"]}
    assert by_name["script.py"]["rendered"] == "print(1)"
    assert "rendered" not in by_name["requirements.txt"]


def test_unknown_input_name_is_an_error_naming_what_is_available():
    with pytest.raises(KeyError, match="requirements.txt"):
        set_execution_unit_input(_unit(), "nope.txt", "x")
