import pytest
from mat3ra.notebooks_utils.workflow import apply_scf_kgrid, patch_workflow_qe_input
from mat3ra.standata.workflows import WorkflowStandata
from mat3ra.wode.workflows import Workflow

FIXED_CELL_RELAXATION = "fixed_cell_relaxation.json"
RELAX_UNIT_NAMES = ["pw_relax"]
SURFACE_ENERGY_WORKFLOW = "surface_energy.json"
SCF_KGRID = [4, 4, 1]


def _relax_workflow():
    config = WorkflowStandata.filter_by_application("espresso").get_by_name_first_match(FIXED_CELL_RELAXATION)
    return Workflow.create(config)


def _pw_relax_content(workflow):
    return workflow.subworkflows[0].get_unit_by_name(name="pw_relax").input[0].template.content


@pytest.mark.parametrize(
    "parameters,present,absent,error",
    [
        (
            {"system": {"vdw_corr": "d3_grimme"}, "electrons": {"mixing_beta": 0.5, "diago_full_acc": True}},
            ["vdw_corr = 'd3_grimme'", "{{ input.IBRAV }}", "mixing_beta = 0.5", "diago_full_acc = .true."],
            ["mixing_beta = 0.3"],
            None,
        ),
        ({"FAKESECTION": {"x": 1}}, [], [], "Namelist '&FAKESECTION' not found."),
    ],
)
def test_patch_workflow_qe_input(parameters, present, absent, error):
    workflow = _relax_workflow()
    if error:
        with pytest.raises(ValueError, match=error):
            patch_workflow_qe_input(workflow, parameters, unit_names=RELAX_UNIT_NAMES)
        return
    patch_workflow_qe_input(workflow, parameters, unit_names=RELAX_UNIT_NAMES)
    content = _pw_relax_content(workflow)
    for text in present:
        assert text in content
    for text in absent:
        assert text not in content


def _surface_workflow():
    config = WorkflowStandata.filter_by_application("espresso").get_by_name_first_match(SURFACE_ENERGY_WORKFLOW)
    return Workflow.create(config)


def test_apply_scf_kgrid_updates_pw_scf_context():
    workflow = _surface_workflow()
    apply_scf_kgrid(workflow, scf_kgrid=SCF_KGRID, first_only=True)
    unit = next(
        subworkflow.get_unit_by_name(name="pw_scf")
        for subworkflow in workflow.subworkflows
        if subworkflow.get_unit_by_name(name="pw_scf")
    )
    assert any(item.get("name") == "kgrid" or "dimensions" in item for item in unit.context)
