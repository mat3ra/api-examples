#!/usr/bin/env python3
"""UTK run dir -> platform documents (sample set, samples, measurement, one hysteresis-loop property per sample),
validated against the ESSE schemas, then uploaded through the REST API.

Ad hoc parser for SOF-8050. Field kinds follow ONTOLOGY.md. The property model follows PLAN-S3-loop-property.md:
the property is the pad's hysteresis loop — the eight loops combined — with the loop parameters (mean, population
standard deviation, count over the loops) inside it. Individual loops stay in the measurement's metadata.

    upload_run.py <run_dir> --physical-id <id> --account <slug>                      # upload everything
    upload_run.py <run_dir> --physical-id <id> --dry-run [--emit-example out.json]   # parse + validate only; write one property as the ESSE example
    upload_run.py <folder> --physical-id <id> --nlr <xrf instrument> <iv instrument>  # NLR's XRF grid and DC I-V sweep instead of a UTK run

Requires Python 3.9+ and `pip install mat3ra-api-client`, which talks to the platform and takes OIDC_ACCESS_TOKEN, or
ACCOUNT_ID + AUTH_TOKEN (an API token from Preferences), from the environment; MAT3RA_HOST picks the host. Optional:
`pip install mat3ra-esse` (tested with 2026.8.27-0) turns on schema validation before anything is uploaded.

Canonical copy: mat3ra/api-examples `examples/measurement/upload_run.py`, beside the notebook that imports it. The
planning repo keeps a working copy and the tests; scripts/publish.sh copies api-examples → plan by default and
plan → api-examples with --push.
"""
import argparse, ast, concurrent.futures, json, math, os, re, statistics, struct, sys, threading, time, urllib.parse, uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from mat3ra.api_client import APIClient

try:  # optional: schema validation before anything is sent
    from mat3ra.esse import ESSE
    from mat3ra.esse.models.sample import SampleSchema
except ImportError:
    ESSE = SampleSchema = None

FIELD = {"off_field": "off", "on_field": "on"}
# loop_params key -> parameters path (units: voltages in xAxis.units, responses in yAxis.units)
PARAMETERS = {
    "imprint_v": ("imprint",),
    "v_c_rising": ("coerciveVoltage", "rising"),
    "v_c_falling": ("coerciveVoltage", "falling"),
    "loop_width_v": ("loopWidth",),
    "loop_height_m": ("loopHeight",),
    "remnant_rising_m": ("remanentResponse", "rising"),
    "remnant_falling_m": ("remanentResponse", "falling"),
}
INSTRUMENT = {"name": "asylum-spm", "shortName": "spm", "summary": "Asylum Research SPM driven by afm-lib (switching-spectroscopy PFM)",
              "version": "1.0", "build": "afm-lib", "isUsingMaterial": False, "hasAdvancedComputeOptions": False}
g = lambda v: float(f"{v:.6g}")


def load_npy(path):
    """A one-dimensional float32/float64 .npy file as a list of floats (no numpy: the format is a header + raw values)."""
    data = Path(path).read_bytes()
    if data[:6] != b"\x93NUMPY":
        raise ValueError(f"{path}: not a .npy file")
    header_length = struct.unpack("<H", data[8:10])[0]
    header = ast.literal_eval(data[10:10 + header_length].decode())
    count = header["shape"][0]
    try:
        item_format = {"<f4": "f", "<f8": "d"}[header["descr"]]
    except KeyError:
        raise ValueError(f"{path}: unsupported dtype {header['descr']}") from None
    start = 10 + header_length
    return list(struct.unpack("<%d%s" % (count, item_format), data[start:start + count * struct.calcsize(item_format)]))


def load_run(run_dir):
    """UTK's consolidated summary.json (run, recipe, status_at_start, measurements[]) or a run dir with
    recipe.json + session.json + records/*.json — the same fields under different keys."""
    summary = run_dir / "summary.json"
    if summary.exists():
        d = json.loads(summary.read_text())
        session = dict(d["run"]); session["status_at_start"] = d.get("status_at_start")
        records = []
        for m in d["measurements"]:
            stem = Path(m["segmentation"]["bias_on_path"].replace(chr(92), "/")).parent.name
            records.append({"labels": m["labels"], "file_path": m["file_path"], "out_stem": stem,
                            "requested_params": m["requested"], "instrument_params": m["achieved"],
                            "loop_params": m["loop_params"], "channel_stats": m.get("channel_stats")})
        return d["recipe"], session, records
    recipe = json.loads((run_dir / "recipe.json").read_text())
    session = json.loads((run_dir / "session.json").read_text()) if (run_dir / "session.json").exists() else {}
    records = [json.loads(p.read_text()) for p in sorted((run_dir / "records").glob("*.json"))]
    return recipe, session, records


def response_curve(loops_dir, field, phase_offset_deg, bias):
    """UTK's X': rotate the lock-in quadratures by the loop's PCA angle so the switching lands in x',
    sign pinned so x' rises with bias (extract_loop_params). None if the arrays are not all present."""
    try:
        x, y = load_npy(loops_dir / f"X_{field}.npy"), load_npy(loops_dir / f"Y_{field}.npy")
    except (FileNotFoundError, ValueError):
        return None
    phi = math.radians(phase_offset_deg)
    xr = [a * math.cos(phi) + b * math.sin(phi) for a, b in zip(x, y)]
    mb, mx = statistics.fmean(bias), statistics.fmean(xr)
    if sum((b - mb) * (v - mx) for b, v in zip(bias, xr)) < 0:
        xr = [-v for v in xr]
    return xr


def pointwise_mean(curves):
    """The mean curve of several curves sampled on the same bias axis."""
    return [g(statistics.fmean(values)) for values in zip(*curves)]


def parameter_statistics(values):
    """One loop parameter over the loops of a sample: mean, population standard deviation, count."""
    return {"value": g(statistics.fmean(values)),
            "standardDeviation": g(statistics.pstdev(values)) if len(values) > 1 else 0.0, "count": len(values)}


def combine_pad(label, records, run_dir):
    """One hysteresis_loop property for a pad: point-wise mean of the response over its loops (on and off), and
    each loop parameter as mean / spread / count over the loops. None when no loop has curves."""
    bias, series, params = None, {"on": [], "off": []}, {"on": {}, "off": {}}
    for r in records:
        loops_dir = run_dir / "loops" / (r.get("out_stem") or Path(r["file_path"]).stem)
        for branch, field in FIELD.items():
            lp = r["loop_params"].get(branch) or {}
            for key, path in PARAMETERS.items():
                if lp.get(key) is not None:
                    params[field].setdefault(path, []).append(lp[key])
            bias_p = loops_dir / f"bias_{field}.npy"
            if not bias_p.exists() or lp.get("phase_offset_deg") is None:
                continue
            b = load_npy(bias_p)
            bias = bias or b
            curve = response_curve(loops_dir, field, lp["phase_offset_deg"], b)
            # averaged point by point, so a loop measured on a different bias axis is dropped rather
            # than folded in: same length is not the same voltages
            if curve is not None and same_axis(b, bias):
                series[field].append(curve)
    if bias is None or not series["on"] or not series["off"]:
        return None
    parameters = {}
    for field in ("on", "off"):
        block = {}
        for path, vals in params[field].items():
            node = block
            for k in path[:-1]:
                node = node.setdefault(k, {})
            node[path[-1]] = parameter_statistics(vals)
        parameters[field] = block
    return {"name": "hysteresis_loop", "legend": ["on", "off"],
            "xAxis": {"label": "bias", "units": "V"}, "yAxis": {"label": "response", "units": "m"},
            "xDataArray": [g(v) for v in bias], "yDataSeries": [pointwise_mean(series["on"]), pointwise_mean(series["off"])],
            "parameters": parameters}


WORKFLOW_NAMESPACE = uuid.UUID("6f3b0b0e-8c1e-4b7a-9f21-3a5f0e2d1c44")  # stable ids: the same workflow every upload


def build_workflow(recipe, labels):
    """The procedure that runs on UTK's Asylum SPM, the same shape as standata's `asylum-spm/ss_pfm` workflow: ONE
    workflow "SS-PFM Hysteresis Loop", one subworkflow `ss_pfm`, one execution unit `run_loop` declaring
    `hysteresis_loop`. It is the same workflow for every sample in the set — the measurement is not re-planned per
    sample — and its ids are stable (uuid5 of the unit names), so a property's `source.info.unitId` means the same
    thing across uploads. Application / executable / flavor are the standata registry entries (asylum-spm / loop /
    ss_pfm) so the platform resolves the unit exactly as it does a job's. The recipe travels in metadata."""
    result = [{"name": "hysteresis_loop"}]
    monitors = [{"name": "standard_output"}]
    executable = {"name": "loop", "applicationName": INSTRUMENT["name"], "applicationVersion": "*", "isDefault": True,
                  "monitors": monitors, "results": result, "preProcessors": [], "postProcessors": []}
    flavor = {"name": "ss_pfm", "executableName": "loop", "applicationName": INSTRUMENT["name"], "applicationVersion": "*",
              "isDefault": True, "input": [], "monitors": monitors, "results": result, "preProcessors": [], "postProcessors": []}
    unit = {"type": "execution", "name": "run_loop", "flowchartId": uuid.uuid5(WORKFLOW_NAMESPACE, "run_loop").hex[:24], "head": True, "status": "finished",
            "application": INSTRUMENT, "executable": executable, "flavor": flavor, "input": [], "context": [],
            "monitors": monitors, "results": result, "preProcessors": [], "postProcessors": []}
    # ESSE requires a model on every subworkflow; an experiment has none, so the legacy "unknown" model.
    model = {"type": "unknown", "subtype": "unknown", "method": {"type": "unknown", "subtype": "unknown"}}
    sw_id = uuid.uuid5(WORKFLOW_NAMESPACE, "ss_pfm").hex[:17]
    subworkflow = {"_id": sw_id, "name": "ss_pfm", "application": INSTRUMENT, "model": model,
                   "properties": ["hysteresis_loop"], "units": [unit]}
    # A subworkflow unit carries the subworkflow's own `_id` — that is how the platform pairs them.
    sw_unit = {"_id": sw_id, "type": "subworkflow", "name": subworkflow["name"], "flowchartId": uuid.uuid5(WORKFLOW_NAMESPACE, "ss_pfm/unit").hex[:24],
               "head": True, "status": "finished", "preProcessors": [], "postProcessors": [], "monitors": [], "results": []}
    return {"name": "SS-PFM Hysteresis Loop", "isDefault": False, "tags": ["experimental", "afm"], "properties": ["hysteresis_loop"],
            "application": INSTRUMENT, "subworkflows": [subworkflow], "units": [sw_unit], "workflows": [],
            "metadata": {"recipe": recipe, "loop_settings": recipe["per_site"][0]["loop_settings"], "sites": list(labels)}}



RECORD_GROUPS = ("labels", "file_path", "requested_params", "instrument_params", "loop_params", "channel_stats")
SAMPLE_KEY = "labels.site_label"  # a record's reference to its sample — stays on every record


def _flatten(d, prefix=""):
    """Nested dict → one level, keys joined with dots."""
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _unflatten(flat):
    """The inverse of _flatten."""
    out = {}
    for key, v in flat.items():
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = v
    return out


def _constant_keys(flat_rows):
    """Keys present in every row with the same value everywhere. A key one row lacks is not constant, even if the
    rows that have it agree — otherwise a group that is null on one record and absent on another looks shared."""
    if not flat_rows:
        return set()
    keys = set.intersection(*(set(row) for row in flat_rows))
    return {k for k in keys if all(row[k] == flat_rows[0][k] for row in flat_rows)}


def factor_records(records):
    """Each record keeps only what is unique to it. Fields identical across the whole run move to the measurement
    (`common`); fields identical across one sample's records move to that sample's metadata; the record keeps its
    sample reference and the values that actually vary per loop (measured 128 → 43 / 4 / 81 on the 704-record run)."""
    if not records:
        return {}, {}, []
    flat = [_flatten({k: r.get(k) for k in RECORD_GROUPS}) for r in records]
    common_keys = _constant_keys(flat) - {SAMPLE_KEY}
    by_sample = {}
    for row in flat:
        by_sample.setdefault(row[SAMPLE_KEY], []).append(row)
    sample_keys = set.intersection(*(_constant_keys(rows) for rows in by_sample.values())) - common_keys - {SAMPLE_KEY}
    # a group can be a dict on one record and null on another: read with .get, never index
    common = _unflatten({k: flat[0].get(k) for k in sorted(common_keys)})
    per_sample = {label: _unflatten({k: rows[0].get(k) for k in sorted(sample_keys)}) for label, rows in by_sample.items()}
    slim = [_unflatten({k: v for k, v in row.items() if k not in common_keys and k not in sample_keys}) for row in flat]
    return common, per_sample, slim

def starting_site(recipe):
    """The site the run started from: r0c00 when the recipe has it, else the first one listed."""
    return next((s for s in recipe["sites"] if s["label"] == "r0c00"), recipe["sites"][0])


def thinned_curves(prop, points=12):
    """The curves at `points` evenly spaced samples: an ESSE example shows the shape, not the data."""
    x = prop["xDataArray"]
    if len(x) <= points:
        return {}
    keep = [round(i * (len(x) - 1) / (points - 1)) for i in range(points)]
    return {"xDataArray": [x[i] for i in keep],
            "yDataSeries": [[s[i] for i in keep] for s in prop["yDataSeries"]]}


def registration(recipe):
    """The instrument's frame as UTK stated it: one anchor in words (from recipe.context) and where the run started
    on the stage. Recorded, not interpreted."""
    ctx = recipe.get("context", "")
    m = re.search(r"starting point is (.+?)(?:\.|$)", ctx)
    r0 = starting_site(recipe)
    return {"frame": "asylum-spm stage", "units": "m", "anchor": m.group(1).strip() if m else ctx,
            f"{r0['label']}_stage_m": [r0["x_stage_m"], r0["y_stage_m"]]}


def sample_files(label, records, run_dir, slim_by_index):
    """Files of one sample's measurement: one JSON per record (the fields unique to it) and, when the run folder has them,
    the loop arrays and annotated plots. Returned as (relative name, payload) where payload is text or a Path."""
    out = []
    for r, slim in zip(records, slim_by_index):
        step, point = r["labels"].get("step_index", 0), r["labels"].get("point_index", 0)
        out.append((f"records/step{step}_pt{point:02d}.json", json.dumps(slim, indent=1)))
        d = run_dir / "loops" / r.get("out_stem", "")
        if r.get("out_stem") and d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix in (".npy", ".png"):
                    out.append((f"loops/{d.name}/{f.name}", f))
    return out


def parse(run_dir, physical_id, limit_records=None, deposition=None, instrument="asylum-afm"):
    """The whole run folder as platform documents: sample set, samples, measurement set, one measurement per sample, files, one loop property per fully measured sample."""
    run_dir = Path(run_dir)
    recipe, session, all_records = load_run(run_dir)
    records = all_records[:limit_records] if limit_records else all_records
    if not physical_id:
        raise ValueError("--physical-id: the identifier written on the physical piece is required")
    run_name = session.get("name") or run_dir.name
    reg = registration(recipe)
    sample_set = {"name": run_name, "entitySetType": "ordered", "metadata": {}}
    # NLR's HTEM deposition record(s) for the piece, verbatim. UTK drops the file into
    # the run folder as deposition*.json; --deposition overrides that.
    deposition_files = [Path(deposition)] if deposition else sorted(run_dir.glob("deposition*.json"))
    if deposition_files:
        deposition_records = []
        for f in deposition_files:
            d = json.loads(f.read_text())
            deposition_records.extend(d if isinstance(d, list) else [d])
        sample_set["metadata"]["deposition"] = deposition_records
    # the photograph of the piece: any image at the run-folder root
    images = [f for f in sorted(run_dir.iterdir()) if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    # samples in recipe order (the set is ordered; the server assigns inSet.index as they are moved in)
    samples = {s["label"]: {"name": f"{physical_id} {s['label']}", "label": s["label"], "physicalId": physical_id,
                            "position": {"coordinates": [s["x_stage_m"], s["y_stage_m"]], "units": "m"},
                            "metadata": {"registration": reg}}
               for s in recipe["sites"]}
    if limit_records:
        # a trial run must be a prefix of a full one: only samples whose records ALL made the cut, so no sample is
        # ever published with a partial loop count that a full run would then skip as "already there"
        full_counts, kept_counts = {}, {}
        for r in all_records:
            full_counts[r["labels"]["site_label"]] = full_counts.get(r["labels"]["site_label"], 0) + 1
        for r in records:
            kept_counts[r["labels"]["site_label"]] = kept_counts.get(r["labels"]["site_label"], 0) + 1
        complete = {label for label, n in kept_counts.items() if n == full_counts[label]}
        records = [r for r in records if r["labels"]["site_label"] in complete]
        samples = {label: sample for label, sample in samples.items() if label in complete}
    common, per_sample, slim_records = factor_records(records)
    for label, const in per_sample.items():
        if label in samples:
            samples[label]["metadata"].update(const)
    workflow = build_workflow(recipe, list(samples))
    unit_id = workflow["subworkflows"][0]["units"][0]["flowchartId"]
    measurement_set = {"name": run_name, "entitySetType": "ordered",
                       "metadata": {"session": session, "recipe": recipe["name"], "context": recipe.get("context", ""),
                                    "common": common, "registration": reg}}
    # the setup block, Measurement : setup :: Job : compute — the machine and the sitting; the technique
    # (asylum-spm, SS-PFM) is the workflow's application. The run folder does not name the machine: --instrument does.
    started = session.get("started_ts")
    setup_block = {"name": instrument,
                        "session": {k: v for k, v in {"name": session.get("name"),
                                                      "started": datetime.fromtimestamp(started, timezone.utc).isoformat().replace("+00:00", "Z") if started else None}.items() if v},
                        **({"settings": common["instrument_params"]} if common.get("instrument_params") else {})}
    by_sample, slim_by_sample = {}, {}
    for r, slim in zip(records, slim_records):
        lab = r["labels"]["site_label"]
        by_sample.setdefault(lab, []).append(r); slim_by_sample.setdefault(lab, []).append(slim)
    # one measurement per sample: Measurement : Sample :: Job : Material
    measurements, files, properties, skipped = {}, {}, [], []
    for label in samples:
        recs = by_sample.get(label, [])
        measurements[label] = {"name": f"{run_name} {label}", "_sample": None, "workflow": workflow,
                               "setup": setup_block, "status": "finished",
                               "metadata": {"run_dir": session.get("run_dir", str(run_dir)), "recordsCount": len(recs)}}
        slim_by_label = slim_by_sample.get(label, [])
        measurements[label]["_records"] = slim_by_label  # not sent; upload() decides files vs metadata
        files[label] = sample_files(label, recs, run_dir, slim_by_sample.get(label, []))
        prop = combine_pad(label, recs, run_dir) if recs else None
        (properties.append((label, unit_id, prop, 0)) if prop else skipped.append(label))
    return {"physicalId": physical_id, "run": run_name, "sample_set": sample_set, "images": images, "samples": samples,
            "measurement_set": measurement_set, "measurements": measurements, "files": files, "set_files": [],
            "records": records, "properties": properties, "skipped": skipped}


NLR_FRAME = {"frame": "wafer", "units": "mm", "note": "x_mm, y_mm as delivered by NLR; corner and axes to be confirmed"}
XRF_APPLICATION = {"name": "xrf-mapper", "shortName": "xrf", "summary": "X-ray fluorescence mapper (film thickness and composition over a grid of positions)",
                   "version": "1.0", "build": "Default", "isUsingMaterial": False, "hasAdvancedComputeOptions": False}
IV_APPLICATION = {"name": "probe-station", "shortName": "iv", "summary": "DC probe station (current through a pad over a bias sweep)",
                  "version": "1.0", "build": "Default", "isUsingMaterial": False, "hasAdvancedComputeOptions": False}


def read_columns(path):
    """Every line of a tab-separated file after its header, split into its cells."""
    return [line.split("\t") for line in Path(path).read_text().splitlines()[1:] if line.strip()]


def build_nlr_workflow(application, executable_name, flavor_name, name, properties):
    """The procedure one of NLR's instruments runs, in the shape build_workflow gives UTK's: ONE workflow, one
    subworkflow, one execution unit declaring what it produces, ids stable across uploads (uuid5 of the names).
    Application, executable and flavor name the standata registry entries these two instruments still need."""
    results = [{"name": property_name} for property_name in properties]
    monitors = [{"name": "standard_output"}]
    executable = {"name": executable_name, "applicationName": application["name"], "applicationVersion": "*", "isDefault": True,
                  "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    flavor = {"name": flavor_name, "executableName": executable_name, "applicationName": application["name"], "applicationVersion": "*",
              "isDefault": True, "input": [], "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    unit = {"type": "execution", "name": executable_name, "head": True, "status": "finished",
            "flowchartId": uuid.uuid5(WORKFLOW_NAMESPACE, f"{application['name']}/{executable_name}").hex[:24],
            "application": application, "executable": executable, "flavor": flavor, "input": [], "context": [],
            "monitors": monitors, "results": results, "preProcessors": [], "postProcessors": []}
    model = {"type": "unknown", "subtype": "unknown", "method": {"type": "unknown", "subtype": "unknown"}}
    subworkflow_id = uuid.uuid5(WORKFLOW_NAMESPACE, f"{application['name']}/{flavor_name}").hex[:17]
    subworkflow = {"_id": subworkflow_id, "name": flavor_name, "application": application, "model": model,
                   "properties": properties, "units": [unit]}
    subworkflow_unit = {"_id": subworkflow_id, "type": "subworkflow", "name": flavor_name, "head": True, "status": "finished",
                        "flowchartId": uuid.uuid5(WORKFLOW_NAMESPACE, f"{application['name']}/{flavor_name}/unit").hex[:24],
                        "preProcessors": [], "postProcessors": [], "monitors": [], "results": []}
    return {"name": name, "isDefault": False, "tags": ["experimental"], "properties": properties, "application": application,
            "subworkflows": [subworkflow], "units": [subworkflow_unit], "workflows": []}


def parse_nlr(folder, physical_id, xrf_instrument, iv_instrument):
    """NLR's delivery for one piece as platform documents: one Sample Set of the pads they measured, and one run per
    technique over those same pads — the XRF map, then the DC I-V sweep. Two runs, each in the shape parse() returns,
    so upload() takes them one after the other: the first creates the Sample Set, the second finds it by name."""
    folder = Path(folder)
    grid_file = sorted(folder.rglob("*xrf_grid.txt"))[0]
    volts_file, amps_file = sorted(folder.rglob("IV_Volts.txt"))[0], sorted(folder.rglob("IV_Amps.txt"))[0]
    run_name = grid_file.stem
    images = [f for f in sorted(folder.rglob("*")) if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    sample_set = {"name": run_name, "entitySetType": "ordered", "metadata": {}}
    xrf_run_name = f"{run_name} XRF"
    xrf_workflow = build_nlr_workflow(XRF_APPLICATION, "map", "xrf_grid", "XRF Grid Map",
                                      ["thickness", "al_atomic_fraction", "sc_atomic_fraction"])
    xrf_unit_id = xrf_workflow["subworkflows"][0]["units"][0]["flowchartId"]
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
    iv_workflow = build_nlr_workflow(IV_APPLICATION, "sweep", "dc_iv", "DC I-V Sweep", ["iv_curve"])
    iv_unit_id = iv_workflow["subworkflows"][0]["units"][0]["flowchartId"]
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


def holder(prop, measurement_id, sample_id, unit_id, repetition):
    """The property holder the platform stores: the data, where it came from (measurement, sample, workflow unit) and a
    repetition index — 0, since a measurement holds one sample and one loop property."""
    return {"data": prop,
            "source": {"type": "external",
                       "info": {"origin": {"_id": measurement_id, "cls": "Measurement"},
                                "subject": {"_id": sample_id, "cls": "Sample"},
                                "unitId": unit_id}},
            "exabyteId": [], "repetition": repetition}


def validate(parsed):
    """Validate every document against the ESSE schemas; returns the number of invalid ones. Skipped (returns 0) when the
    optional mat3ra-esse package is not installed."""
    if ESSE is None:
        print("schema validation skipped: `pip install mat3ra-esse` to enable it", flush=True)
        return 0
    esse = ESSE()
    schemas = {x["$id"]: x for x in esse.schemas}
    errors = 0
    for smp in parsed["samples"].values():
        try:
            SampleSchema(**smp); esse.validate(smp, schemas["sample"])
        except Exception as e:
            errors += 1; print("SAMPLE INVALID", smp["label"], str(e)[:200])
    for label, m in parsed["measurements"].items():
        m = {k: v for k, v in m.items() if k != "_records"}; m["_sample"] = {"_id": "dryrun", "cls": "Sample", "slug": label}
        try:
            esse.validate(m, schemas["measurement"])
        except Exception as e:
            errors += 1; print("MEASUREMENT INVALID", label, str(e)[:300]); break
    unvalidated = set()
    for label, uid, prop, rep in parsed["properties"]:
        # by the property's own name: NLR's thickness, atomic fractions and I-V curve are not the
        # hysteresis loop, and ESSE has no schema for them yet, so they are reported, not failed
        schema_id = f"properties-directory/non-scalar/{prop['name'].replace('_', '-')}"
        schema = schemas.get(schema_id) or schemas.get(schema_id.replace("non-scalar", "scalar"))
        if schema is None:
            unvalidated.add(prop["name"]); continue
        try:
            esse.validate(prop, schema)
            esse.validate(holder(prop, "dryrun", "dryrun", uid, rep), schemas["property/holder"])
        except Exception as e:
            errors += 1; print("PROPERTY INVALID", label, str(e)[:300])
    if unvalidated:
        print("no ESSE schema yet, not validated:", ", ".join(sorted(unvalidated)))
    return errors


def same_axis(candidate, reference, tolerance=1e-9):
    """Whether two bias axes are the same sweep: equal length and equal voltages within tolerance."""
    return len(candidate) == len(reference) and all(
        abs(a - b) <= tolerance + 1e-6 * abs(b) for a, b in zip(candidate, reference))


def base_url(host):
    """`https://` unless told otherwise: a bare hostname becomes https, localhost/127.0.0.1 http, a URL is kept."""
    host = host.rstrip("/")
    if host.startswith(("http://", "https://")):
        return host
    return ("http://" if host.split(":")[0] in ("localhost", "127.0.0.1") else "https://") + host


def find(endpoint, query, owner_id, limit=100):
    """The account's entities matching `query` — a query bypasses the route's account scoping, so every lookup is
    narrowed. A page as long as the limit is refused: a missed member means a duplicate on the next run."""
    found = endpoint.list(dict(query, **{"owner._id": owner_id}), {"limit": limit})
    if len(found) >= limit and limit > 1:
        raise SystemExit(f"{endpoint.name}: more than {limit} match — this script cannot page yet; stop rather than duplicate")
    return found


def account_id(client, slug_or_name):
    """`--account <slug>` → the id of that account: the slug the platform shows it under, else its display name."""
    accounts = client.list_accounts()
    for field in ("slug", "name"):
        account = next((a for a in accounts if a.get(field) == slug_or_name), None)
        if account:
            return account["_id"]
    raise SystemExit(f"account '{slug_or_name}' is not one of yours: "
                     f"{', '.join(a.get('slug') or a['name'] for a in accounts)}")


THREAD = threading.local()


def thread_client(client):
    """A client of the calling thread's own: the endpoints keep the last response on the connection they share, so
    the file workers cannot use one between them. Building one costs nothing — no request is made until it is used."""
    if not hasattr(THREAD, "client"):
        THREAD.client = APIClient(host=client.host, port=client.port, version=client.version, secure=client.secure,
                                  auth=client.auth, timeout_seconds=client.timeout_seconds)
    return THREAD.client


def put_file(client, name, payload, owner_id):
    """One file into the account's file store: a file on disk through a signed PUT, text through the files route.
    Eight connections at once is enough to make a name resolution fail now and then, so a refused connection is
    tried again twice before it takes the run down with it."""
    for attempt in range(3):
        try:
            if isinstance(payload, Path):
                return client.files.put(payload, name, account_id=owner_id)
            return client.files.create(name, payload, account_id=owner_id)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def merge_metadata(existing, incoming):
    """`incoming` on top of `existing`, keeping what neither replaces. A list grows by the entries it
    does not already hold - a second synthesis run brings deposition records the set has never seen,
    and taking only absent keys would drop them because `deposition` is already there."""
    merged = dict(existing)
    for key, value in incoming.items():
        held = merged.get(key)
        if isinstance(held, list) and isinstance(value, list):
            merged[key] = held + [v for v in value if v not in held]
        elif isinstance(held, dict) and isinstance(value, dict):
            merged[key] = merge_metadata(held, value)
        else:
            merged[key] = value
    return merged


def ensure_set(endpoint, doc, owner_id):
    """The set with this name in the account, created when missing; returns (set, created).
    An existing set takes any metadata it does not have yet - a synthesis run after a measurement
    run has the deposition record to add, and the set was created without it."""
    found = find(endpoint, {"isEntitySet": True, "name": doc["name"]}, owner_id, 5)
    if not found:
        return endpoint.create_set(dict(doc, owner={"_id": owner_id})), True

    existing = found[0]
    merged = merge_metadata(existing.get("metadata") or {}, doc.get("metadata") or {})
    if merged != (existing.get("metadata") or {}):
        endpoint.update_set(existing["_id"], {"metadata": merged})
        existing = dict(existing, metadata=merged)
    return existing, False


def upload(client, parsed, command="both", files="records"):
    """Two imports onto the run's own Sample Set:
    `synthesis`   — NLR's record(s) + the photograph onto the set (created if missing; no samples, no measurements);
    `measurement` — UTK's run: the set, its samples, the measurement set tied to it, one measurement per sample, files, properties;
    `both`        — synthesis if the folder has a deposition record, then measurement.
    Idempotent: sets by run name, members by name/label; files re-put; properties posted only when missing."""
    physical_id, run_name = parsed["physicalId"], parsed["run"]
    owner = {"_id": client.my_account.id}
    has_deposition = "deposition" in parsed["sample_set"]["metadata"]
    sample_set, created_set = ensure_set(client.samples, parsed["sample_set"], owner["_id"])
    set_id = sample_set["_id"]
    if command in ("synthesis", "both") and has_deposition:
        print(f"sample set {set_id} ({run_name}{', created' if created_set else ''}): synthesis record attached")
    if command in ("synthesis", "both") and files != "none":
        for image in parsed["images"]:
            put_file(client, f"sets/{set_id}/{image.name}", image, owner["_id"])
            print(f"  image {image.name} -> sets/{set_id}/")
    if command == "synthesis":
        return
    in_set = {s.get("label"): s for s in find(client.samples, {"inSet._id": set_id, "isEntitySet": {"$ne": True}}, owner["_id"], 500)}
    sample_ids, created = {}, 0
    for label, sample_doc in parsed["samples"].items():
        if label in in_set:
            sample_ids[label] = in_set[label]["_id"]
            continue
        doc = client.samples.create(dict(sample_doc, owner=owner))
        client.samples.move_to_set(doc["_id"], None, set_id)
        sample_ids[label] = doc["_id"]
        created += 1
    print(f"sample set {set_id} ({sample_set['name']}, ordered{', created' if created_set else ''}): {len(sample_ids)} samples, {created} created")
    measurement_set, created_measurement_set = ensure_set(client.measurements, parsed["measurement_set"], owner["_id"])
    existing = {m["name"]: m for m in find(client.measurements, {"inSet._id": measurement_set["_id"], "isEntitySet": {"$ne": True}}, owner["_id"], 500)}
    measurement_ids, measurements_created = {}, 0
    for label, measurement_doc in parsed["measurements"].items():
        if measurement_doc["name"] in existing:
            measurement_ids[label] = existing[measurement_doc["name"]]["_id"]
            continue
        body = {k: v for k, v in measurement_doc.items() if k != "_records"}
        body["_sample"] = {"_id": sample_ids[label], "cls": "Sample"}
        if files == "none":  # no file store: keep the raw records in the measurement's metadata
            body["metadata"] = dict(body["metadata"], records=measurement_doc["_records"])
        doc = client.measurements.create(dict(body, owner=owner))
        client.measurements.move_to_set(doc["_id"], None, measurement_set["_id"])
        measurement_ids[label] = doc["_id"]
        measurements_created += 1
    print(f"measurement set {measurement_set['_id']} ({run_name}, ordered{', created' if created_measurement_set else ''}): "
          f"{len(measurement_ids)} measurements, {measurements_created} created")
    if files != "none":
        # One request per file (~1-2 s each), so: the record JSONs by default, the loop arrays and plots only with
        # --files all, and eight uploads in flight at a time.
        jobs = [(f"measurements/{measurement_set['_id']}/{name}", payload) for name, payload in parsed["set_files"]]
        jobs += [(f"measurements/{measurement_ids[label]}/{name}", payload)
                 for label, file_list in parsed["files"].items() for name, payload in file_list
                 if files == "all" or not name.startswith("loops/")]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for done, _ in enumerate(pool.map(lambda job: put_file(thread_client(client), *job, owner["_id"]), jobs), 1):
                if done % 200 == 0:
                    print(f"  files: {done}/{len(jobs)}", flush=True)
        print(f"files: {len(jobs)} put under measurements/<id>/ ({'records/*.json, loops/*' if files == 'all' else 'records/*.json; --files all adds loops/*'})")
    posted = 0
    for label, unit_id, prop, repetition in parsed["properties"]:  # properties/create is not idempotent: skip what is there
        present = find(client.properties, {"source.info.origin._id": measurement_ids[label], "data.name": prop["name"],
                                           "repetition": repetition}, owner["_id"], 1)
        if present:
            continue
        client.properties.create(dict(holder(prop, measurement_ids[label], sample_ids[label], unit_id, repetition), owner=owner))
        posted += 1
    print(f"properties: {posted} posted, {len(parsed['properties']) - posted} already present")


def main():
    """Command line: parse, validate, upload."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--physical-id", required=True, help="the identifier written on the physical piece the samples are part of, e.g. PDAC_COM5_01448")
    ap.add_argument("command", nargs="?", choices=["synthesis", "measurement", "both"], default="both",
                    help="synthesis: NLR record + photo onto the set · measurement: UTK run onto the set · both (default)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emit-example", help="write the first combined loop property (most loops) to this path — the ESSE example")
    ap.add_argument("--host", default=os.environ.get("MAT3RA_HOST", "localhost:3000"),
                    help="web app host or URL (or MAT3RA_HOST); https unless localhost, e.g. dev.mat3ra.com")
    ap.add_argument("--account", help="slug of the account the data belongs to (reads scoped to it, writes owned by it)")
    ap.add_argument("--files", choices=["records", "all", "none"], default="records",
                    help="which files to upload per measurement: the record JSONs (default), also the loop arrays and plots (all), or none")
    ap.add_argument("--limit-records", type=int, help="trial: only the first N records and the samples they belong to")
    ap.add_argument("--deposition", help="NLR HTEM record (json) kept in the run's sample set metadata")
    ap.add_argument("--instrument", default="asylum-afm", help="identity of the machine the run was measured on (the run folder does not record it)")
    ap.add_argument("--nlr", nargs=2, metavar=("XRF_INSTRUMENT", "IV_INSTRUMENT"),
                    help="the folder holds NLR's delivery — an XRF grid and a DC I-V sweep over the same pads, measured on these two machines — not a UTK run")
    a = ap.parse_intermixed_args()
    if a.nlr:
        runs = parse_nlr(a.run_dir, a.physical_id, *a.nlr)
        for p in runs:
            print(f"{p['physicalId']}: {len(p['samples'])} samples (ordered set) · run {p['run']}: {len(p['measurements'])} "
                  f"measurements (ordered set, one per sample) · {len(p['records'])} rows -> {len(p['set_files'])} files · "
                  f"{len(p['images'])} image(s) · {len(p['properties'])} properties")
    else:
        runs = [parse(a.run_dir, a.physical_id, a.limit_records, a.deposition, a.instrument)]
        p = runs[0]
        nfiles = sum(len(v) for v in p["files"].values())
        print(f"{p['physicalId']}: {len(p['samples'])} samples (ordered set) · run {p['run']}: {len(p['measurements'])} measurements "
              f"(ordered set, one per sample) · {len(p['records'])} records -> {nfiles} files · {len(p['images'])} image(s) · "
              f"{len(p['properties'])} samples with a combined loop" + (f" · no curves: {len(p['skipped'])} samples" if p["skipped"] else ""))
        for label, _, prop, _rep in p["properties"]:
            n = prop["parameters"]["off"].get("imprint", {}).get("count")
            print(f"  {label}: {n} loops combined, imprint off = {prop['parameters']['off'].get('imprint', {}).get('value')} V")
        if a.emit_example and p["properties"]:
            label, _, prop, _rep = max(p["properties"], key=lambda t: t[2]["parameters"]["off"].get("imprint", {}).get("count", 0))
            prop = dict(prop, **thinned_curves(prop))
            Path(a.emit_example).write_text(json.dumps(prop, indent=4) + "\n"); print(f"example written from sample {label} -> {a.emit_example}")
    errors = sum(validate(p) for p in runs)
    print("validation:", "OK" if errors == 0 else f"{errors} invalid documents")
    if errors or a.dry_run:
        sys.exit(1 if errors else 0)
    url = urllib.parse.urlsplit(base_url(a.host))
    address = {"host": url.hostname, "port": url.port or (443 if url.scheme == "https" else 80), "secure": url.scheme == "https"}
    client = APIClient.authenticate(**address)
    if a.account:
        client = APIClient.authenticate(account_id=account_id(client, a.account), **address)
    for p in runs:
        upload(client, p, command=a.command, files=a.files)


if __name__ == "__main__":
    main()
