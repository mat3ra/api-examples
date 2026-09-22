"""The measurement workflow a parser attaches to its measurements.

An experiment's workflow is a description, not a plan the platform executes: ONE workflow, one subworkflow, one
execution unit that declares what the instrument produces. Application, executable and flavor name the standata
registry entries, so the platform resolves the unit exactly as it does a job's, and the ids are stable (uuid5 of
the names) so a property's `source.info.unitId` means the same thing across uploads.
"""
import uuid

WORKFLOW_NAMESPACE = uuid.UUID("6f3b0b0e-8c1e-4b7a-9f21-3a5f0e2d1c44")
# ESSE requires a model on every subworkflow; an experiment has none, so the legacy "unknown" model.
UNKNOWN_MODEL = {"type": "unknown", "subtype": "unknown", "method": {"type": "unknown", "subtype": "unknown"}}


def build_workflow(application, executable_name, flavor_name, name, properties,
                   unit_name=None, tags=("experimental",), metadata=None, id_prefix=""):
    """`properties` are what the unit declares it produces. `unit_name` defaults to the executable's;
    `id_prefix` scopes the stable ids, so two instruments may share an executable name."""
    unit_name = unit_name or executable_name
    results = [{"name": property_name} for property_name in properties]
    monitors = [{"name": "standard_output"}]
    stable = lambda key, length: uuid.uuid5(WORKFLOW_NAMESPACE, f"{id_prefix}{key}").hex[:length]
    executable = {"name": executable_name, "applicationName": application["name"], "applicationVersion": "*", "isDefault": True,
                  "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    flavor = {"name": flavor_name, "executableName": executable_name, "applicationName": application["name"], "applicationVersion": "*",
              "isDefault": True, "input": [], "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    unit = {"type": "execution", "name": unit_name, "flowchartId": stable(unit_name, 24), "head": True, "status": "finished",
            "application": application, "executable": executable, "flavor": flavor, "input": [], "context": [],
            "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    subworkflow_id = stable(flavor_name, 17)
    subworkflow = {"_id": subworkflow_id, "name": flavor_name, "application": application, "model": UNKNOWN_MODEL,
                   "properties": list(properties), "units": [unit]}
    # A subworkflow unit carries the subworkflow's own `_id` — that is how the platform pairs them.
    subworkflow_unit = {"_id": subworkflow_id, "type": "subworkflow", "name": flavor_name, "flowchartId": stable(f"{flavor_name}/unit", 24),
                        "head": True, "status": "finished", "preProcessors": [], "postProcessors": [], "monitors": [], "results": []}
    workflow = {"name": name, "isDefault": False, "tags": list(tags), "properties": list(properties), "application": application,
                "subworkflows": [subworkflow], "units": [subworkflow_unit], "workflows": []}
    return dict(workflow, metadata=metadata) if metadata is not None else workflow


def unit_id(workflow):
    """The execution unit the properties of this workflow come from."""
    return workflow["subworkflows"][0]["units"][0]["flowchartId"]
