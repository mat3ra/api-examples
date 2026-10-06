"""NLR's delivery for one piece as platform documents: the Library (the piece itself, with its layout and
synthesis), the XRF map as a Sample Set of grid points, and the DC I-V sweep as a Sample Set of pads.

Ad hoc parser for SOF-8050: it reads the tab-separated files NLR ships and nothing else.
"""
import argparse
import json
from pathlib import Path

from mat3ra.standata.workflows import WorkflowStandata

from run_document import serialize


def standata_workflow(application_name, workflow_name):
    """The procedure the instrument runs, from the standata registry — the entry the platform resolves
    a job's workflow through."""
    workflow = WorkflowStandata.find_by_application_and_name(application_name, workflow_name)
    if workflow is None:
        raise LookupError(f"standata has no '{workflow_name}' workflow for {application_name}")
    return workflow


def unit_id(workflow):
    """The execution unit a property of this workflow comes from."""
    return workflow["subworkflows"][0]["units"][0]["flowchartId"]

FRAME = {"origin": "wafer corner", "axes": "x, y", "units": "mm"}
DIMENSIONS = {"shape": "square", "side": 50.8, "units": "mm"}  # a 2-inch substrate
IV_COLUMNS = 11  # the I-V file lists its pads row by row, eleven to a row
XRF_APPLICATION = "xrf-mapper"  # the standata application whose workflow this run records


def read_columns(path):
    """Every line of a tab-separated file after its header, split into its cells."""
    return [line.split("\t") for line in Path(path).read_text().splitlines()[1:] if line.strip()]


IV_APPLICATION = "probe-station"


def parse_nlr(folder, physical_id, xrf_instrument, iv_instrument, description="", deposition=()):
    """NLR's delivery for one piece as two run documents sharing one Library: the XRF map, measured on the bare
    film at the grid points, and the DC I-V sweep, measured on the Pt pads patterned afterwards. The pads are the
    ones NLR probed: the I-V file lists them row by row, IV_COLUMNS to a row, so each pad gets its row and
    column; where each pad sits on the wafer, and its size, come with NLR's pattern and are written onto the
    same pads by label."""
    folder = Path(folder)
    grid_file = sorted(folder.rglob("*xrf_grid.txt"))[0]
    volts_file, amps_file = sorted(folder.rglob("IV_Volts.txt"))[0], sorted(folder.rglob("IV_Amps.txt"))[0]
    run_name = grid_file.stem
    # searched recursively, so the name keeps the subdirectory: two photographs may share a basename
    images = [(f.relative_to(folder).as_posix(), f) for f in sorted(folder.rglob("*"))
              if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    sample_set = {"name": run_name, "entitySetType": "ordered", "metadata": {}}
    xrf_run_name = f"{run_name} XRF"
    xrf_workflow = standata_workflow(XRF_APPLICATION, "XRF Grid Map")
    xrf_unit_id = unit_id(xrf_workflow)
    grid = read_columns(grid_file)
    synthesis = []
    for f in deposition:  # a file may hold one record or a list of them
        record = json.loads(Path(f).read_text())
        synthesis.extend(record if isinstance(record, list) else [record])
    library = {"physicalId": physical_id, "name": physical_id, "description": description,
               "entitySetType": "unordered",
               "metadata": {"dimensions": DIMENSIONS, "frame": FRAME, "synthesis": synthesis}}
    samples, xrf_measurements, xrf_properties = {}, {}, []
    for row, column, x_mm, y_mm, thickness_um, aluminium_at_pct, scandium_at_pct in grid:
        label = f"r{int(row)}c{int(column)}"
        # two rows for one pad would overwrite each other here and leave the row counts below
        # agreeing against a dictionary that has already lost an entry
        if label in samples:
            raise SystemExit(f"{grid_file.name}: pad {label} appears twice")
        samples[label] = {"name": f"{physical_id} {label}", "label": label, "physicalId": physical_id,
                          "position": {"coordinates": [float(x_mm), float(y_mm)], "units": "mm"},
                          "metadata": {"row": int(row), "column": int(column)}}
        xrf_measurements[label] = {"name": f"{xrf_run_name} {label}", "_sample": None, "workflow": xrf_workflow,
                                   "setup": {"name": xrf_instrument}, "status": "finished", "_records": [],
                                   "metadata": {"row": int(row), "column": int(column), "thickness_um": float(thickness_um),
                                                "al_at_pct": float(aluminium_at_pct), "sc_at_pct": float(scandium_at_pct)}}
        # NLR's columns become what ESSE already defines: composition is one elemental_ratio per
        # element, a fraction, not a property named after the element
        xrf_properties += [(label, xrf_unit_id, {"name": "film_thickness", "value": float(thickness_um), "units": "um"}, 0),
                           (label, xrf_unit_id, {"name": "elemental_ratio", "element": "Al", "value": float(aluminium_at_pct) / 100}, 0),
                           (label, xrf_unit_id, {"name": "elemental_ratio", "element": "Sc", "value": float(scandium_at_pct) / 100}, 0)]
    iv_run_name = f"{physical_id} DC IV"
    iv_workflow = standata_workflow(IV_APPLICATION, "DC I-V Sweep")
    iv_unit_id = unit_id(iv_workflow)
    volts = [[float(v) for v in cells] for cells in read_columns(volts_file)]
    amps = [[float(a) for a in cells] for cells in read_columns(amps_file)]
    if len(volts) != len(amps):
        raise SystemExit(f"{volts_file.name}/{amps_file.name}: {len(volts)} and {len(amps)} rows")
    if len(volts) % IV_COLUMNS:
        raise SystemExit(f"{len(volts)} I-V rows do not fill rows of {IV_COLUMNS} pads")
    for row, (bias_row, current_row) in enumerate(zip(volts, amps)):
        if len(bias_row) != len(current_row):
            raise SystemExit(f"row {row}: {len(bias_row)} bias points but {len(current_row)} current points")
    # the pads NLR probed, by their row and column in the file; positions and sizes come with NLR's pattern
    layout = [{"label": f"pad_r{i // IV_COLUMNS}c{i % IV_COLUMNS:02d}", "row": i // IV_COLUMNS, "column": i % IV_COLUMNS,
               "position": None, "extent": None, "stack": None} for i in range(len(volts))]
    library["metadata"]["layout"] = layout
    iv_setup = {"name": iv_instrument, "settings": {"v_min": min(volts[0]), "v_max": max(volts[0]), "points": len(volts[0])}}
    pads, iv_measurements, iv_properties = {}, {}, []
    for index, (pad, bias, current) in enumerate(zip(layout, volts, amps)):
        label = pad["label"]
        pads[label] = {"name": f"{physical_id} {label}", "label": label, "physicalId": physical_id,
                       "metadata": {"site": "pad", "row": pad["row"], "column": pad["column"]}}
        iv_measurements[label] = {"name": f"{iv_run_name} {label}", "_sample": None, "workflow": iv_workflow,
                                  "setup": iv_setup, "status": "finished", "_records": [], "metadata": {"row_index": index}}
        iv_properties.append((label, iv_unit_id, {"name": "current_voltage_curve", "xAxis": {"label": "voltage", "units": "V"},
                                                  "yAxis": {"label": "current", "units": "A"},
                                                  "xDataArray": bias, "yDataSeries": [current]}, 0))
    return [{"physicalId": physical_id, "library": library, "run": xrf_run_name, "sample_set": sample_set, "images": images,
             "samples": samples, "measurement_set": {"name": xrf_run_name, "entitySetType": "ordered", "metadata": {}},
             "measurements": xrf_measurements, "files": {}, "set_files": [(grid_file.name, grid_file)],
             "records": grid, "properties": xrf_properties},
            {"physicalId": physical_id, "library": library, "run": iv_run_name,
             "sample_set": {"name": f"{physical_id} pads", "entitySetType": "ordered", "metadata": {}}, "images": [],
             "samples": pads, "measurement_set": {"name": iv_run_name, "entitySetType": "ordered", "metadata": {}},
             "measurements": iv_measurements, "files": {},
             "set_files": [(volts_file.name, volts_file), (amps_file.name, amps_file)],
             "records": volts, "properties": iv_properties}]



def main():
    """Read NLR's delivery and write its run document."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--physical-id", required=True, help="the identifier written on the physical piece, e.g. PDAC_COM5_01448")
    ap.add_argument("--xrf-instrument", required=True, help="identity of the machine the grid was mapped on")
    ap.add_argument("--iv-instrument", required=True, help="identity of the machine the sweep was measured on")
    ap.add_argument("--description", default="", help="what the piece is, for the Library")
    ap.add_argument("--deposition", nargs="*", default=[], metavar="JSON", help="deposition record(s) for the Library's synthesis")
    ap.add_argument("--out", default="parsed", help="directory for the run documents (default: parsed/)")
    a = ap.parse_args()

    for parsed in parse_nlr(a.folder, a.physical_id, a.xrf_instrument, a.iv_instrument, a.description, a.deposition):
        print(f"{parsed['physicalId']}: {len(parsed['samples'])} samples · run {parsed['run']}: "
              f"{len(parsed['measurements'])} measurements · {len(parsed['records'])} rows -> "
              f"{len(parsed['set_files'])} files · {len(parsed['images'])} image(s) · {len(parsed['properties'])} properties")
        print("run document:", serialize(parsed, a.out, name=parsed["run"].replace(" ", "_") + ".json"))


if __name__ == "__main__":
    main()
