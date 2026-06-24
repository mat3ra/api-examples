import re
from typing import Dict, List, Optional

from mat3ra.wode import Workflow

FORTRAN_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[de][+-]?\d+)?$", re.IGNORECASE)


def _format_fortran_value(value: object) -> str:
    if isinstance(value, bool):
        return f".{str(value).lower()}."
    if isinstance(value, str) and not FORTRAN_NUMBER_PATTERN.match(value):
        return repr(value)
    return str(value)


def patch_workflow_qe_input(
    workflow: Workflow,
    parameters: Dict[str, Dict[str, object]],
    unit_names: List[str],
    input_name: Optional[str] = None,
) -> Workflow:
    """
    Patch QE inputs across workflow subworkflows for named units.

    Args:
        workflow: Workflow with subworkflows.
        parameters: Multi-section parameters {section: {key: val}}.
        unit_names: List of unit names to patch.
        input_name: Optional input file name filter.

    Example:
        patch_workflow_qe_input(workflow, {"system": {"vdw_corr": "d3_grimme"}}, ["pw_relax"])
    """
    # TODO: remove the dict handling when WA is updated, and use latest Standata/Wode/Ade here
    for subworkflow in workflow.subworkflows:
        for unit_name in unit_names:
            if not (unit := subworkflow.get_unit_by_name(name=unit_name)):
                continue
            for input_item in getattr(unit, "input", []):
                if isinstance(input_item, dict):
                    template_name = input_item.get("name")
                    content = input_item.get("content")
                else:
                    template = input_item.template
                    template_name = template.name
                    content = template.content

                if input_name not in (None, template_name):
                    continue

                for section, updates in parameters.items():
                    name = section.lstrip("&")
                    match = re.search(rf"(?ims)(^&{re.escape(name)}\s*\n)(.*?)(^/\s*$)", content)
                    if not match:
                        raise ValueError(f"Namelist '&{name.upper()}' not found.")
                    header, body, footer = match.groups()
                    for key, value in updates.items():
                        line = f"    {key} = {_format_fortran_value(value)}"
                        pattern = rf"(?im)^\s*{re.escape(key)}\s*=.*$"
                        body = re.sub(pattern, line, body) if re.search(pattern, body) else f"{body.rstrip()}\n{line}\n"
                    content = content[: match.start()] + header + body + footer + content[match.end() :]

                if isinstance(input_item, dict):
                    input_item["content"] = content
                else:
                    template.set_content(content)
            subworkflow.set_unit(unit)
    return workflow
