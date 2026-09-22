"""NLR's delivery for one piece as platform documents: one sample set of the pads they measured, and one run per
technique over those same pads — the XRF map, then the DC I-V sweep.

Ad hoc parser for SOF-8050: it reads the tab-separated files NLR ships and nothing else.
"""
from pathlib import Path

from workflow import build_workflow, unit_id

NLR_FRAME = {"frame": "wafer", "units": "mm", "note": "x_mm, y_mm as delivered by NLR; corner and axes to be confirmed"}
XRF_APPLICATION = {"name": "xrf-mapper", "shortName": "xrf", "summary": "X-ray fluorescence mapper (film thickness and composition over a grid of positions)",
                   "version": "1.0", "build": "Default", "isUsingMaterial": False, "hasAdvancedComputeOptions": False}
IV_APPLICATION = {"name": "probe-station", "shortName": "iv", "summary": "DC probe station (current through a pad over a bias sweep)",
                  "version": "1.0", "build": "Default", "isUsingMaterial": False, "hasAdvancedComputeOptions": False}


def read_columns(path):
    """Every line of a tab-separated file after its header, split into its cells."""
    return [line.split("\t") for line in Path(path).read_text().splitlines()[1:] if line.strip()]


def nlr_workflow(application, executable_name, flavor_name, name, properties):
    """NLR's two instruments are not in the standata registry yet, so their ids are scoped by application name."""
    return build_workflow(application, executable_name, flavor_name, name, properties,
                          id_prefix=f"{application['name']}/")


def parse_nlr(folder, physical_id, xrf_instrument, iv_instrument):
    """NLR's delivery for one piece as platform documents: one Sample Set of the pads they measured, and one run per
    technique over those same pads — the XRF map, then the DC I-V sweep. Two runs, each in the shape parse() returns,
    so upload() takes them one after the other: the first creates the Sample Set, the second finds it by name."""
    folder = Path(folder)
    grid_file = sorted(folder.rglob("*xrf_grid.txt"))[0]
    volts_file, amps_file = sorted(folder.rglob("IV_Volts.txt"))[0], sorted(folder.rglob("IV_Amps.txt"))[0]
    run_name = grid_file.stem
    # searched recursively, so the name keeps the subdirectory: two photographs may share a basename
    images = [(f.relative_to(folder).as_posix(), f) for f in sorted(folder.rglob("*"))
              if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    sample_set = {"name": run_name, "entitySetType": "ordered", "metadata": {}}
    xrf_run_name = f"{run_name} XRF"
    xrf_workflow = nlr_workflow(XRF_APPLICATION, "map", "xrf_grid", "XRF Grid Map",
                                ["thickness", "al_atomic_fraction", "sc_atomic_fraction"])
    xrf_unit_id = unit_id(xrf_workflow)
    grid = read_columns(grid_file)
    samples, xrf_measurements, xrf_properties = {}, {}, []
    for row, column, x_mm, y_mm, thickness_um, aluminium_at_pct, scandium_at_pct in grid:
        label = f"r{int(row)}c{int(column)}"
        # two rows for one pad would overwrite each other here and leave the row counts below
        # agreeing against a dictionary that has already lost an entry
        if label in samples:
            raise SystemExit(f"{grid_file.name}: pad {label} appears twice")
        samples[label] = {"name": f"{physical_id} {label}", "label": label, "physicalId": physical_id,
                          "position": {"coordinates": [float(x_mm), float(y_mm)], "units": "mm"},
                          "metadata": {"frame": NLR_FRAME, "row": int(row), "column": int(column)}}
        xrf_measurements[label] = {"name": f"{xrf_run_name} {label}", "_sample": None, "workflow": xrf_workflow,
                                   "setup": {"name": xrf_instrument}, "status": "finished", "_records": [],
                                   "metadata": {"row": int(row), "column": int(column), "thickness_um": float(thickness_um),
                                                "al_at_pct": float(aluminium_at_pct), "sc_at_pct": float(scandium_at_pct)}}
        xrf_properties += [(label, xrf_unit_id, {"name": "thickness", "value": float(thickness_um), "units": "um"}, 0),
                           (label, xrf_unit_id, {"name": "al_atomic_fraction", "value": float(aluminium_at_pct), "units": "at%"}, 0),
                           (label, xrf_unit_id, {"name": "sc_atomic_fraction", "value": float(scandium_at_pct), "units": "at%"}, 0)]
    iv_run_name = f"{run_name} DC IV"
    iv_workflow = nlr_workflow(IV_APPLICATION, "sweep", "dc_iv", "DC I-V Sweep", ["iv_curve"])
    iv_unit_id = unit_id(iv_workflow)
    volts = [[float(v) for v in cells] for cells in read_columns(volts_file)]
    amps = [[float(a) for a in cells] for cells in read_columns(amps_file)]
    # zip would silently drop pads, so the shapes are checked before any document is built
    if not (len(grid) == len(volts) == len(amps)):
        raise SystemExit(f"{volts_file.name}/{amps_file.name}: {len(volts)}/{len(amps)} rows for "
                         f"{len(grid)} pads in {grid_file.name} — every pad needs one row in each file")
    for row, (bias_row, current_row) in enumerate(zip(volts, amps)):
        if len(bias_row) != len(current_row):
            raise SystemExit(f"row {row}: {len(bias_row)} bias points but {len(current_row)} current points")
    # the sweep NLR ran, read off the voltages themselves; every row of the file holds the same one
    iv_setup = {"name": iv_instrument, "settings": {"v_min": min(volts[0]), "v_max": max(volts[0]), "points": len(volts[0])}}
    iv_measurements, iv_properties = {}, []
    for index, (label, bias, current) in enumerate(zip(samples, volts, amps)):
        iv_measurements[label] = {"name": f"{iv_run_name} {label}", "_sample": None, "workflow": iv_workflow,
                                  "setup": iv_setup, "status": "finished", "_records": [], "metadata": {"row_index": index}}
        iv_properties.append((label, iv_unit_id, {"name": "iv_curve", "xAxis": {"label": "bias", "units": "V"},
                                                  "yAxis": {"label": "current", "units": "A"},
                                                  "xDataArray": bias, "yDataSeries": [current]}, 0))
    return [{"physicalId": physical_id, "run": xrf_run_name, "sample_set": sample_set, "images": images, "samples": samples,
             "measurement_set": {"name": xrf_run_name, "entitySetType": "ordered", "metadata": {}},
             "measurements": xrf_measurements, "files": {}, "set_files": [(grid_file.name, grid_file)],
             "records": grid, "properties": xrf_properties},
            {"physicalId": physical_id, "run": iv_run_name, "sample_set": sample_set, "images": images, "samples": samples,
             "measurement_set": {"name": iv_run_name, "entitySetType": "ordered", "metadata": {}},
             "measurements": iv_measurements, "files": {}, "set_files": [(volts_file.name, volts_file), (amps_file.name, amps_file)],
             "records": volts, "properties": iv_properties}]

