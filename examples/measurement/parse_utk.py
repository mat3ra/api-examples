"""A UTK SS-PFM run folder as platform documents: a sample set of the pads, one measurement per pad, and one
hysteresis-loop property per pad — the eight loops combined, with the loop parameters (mean, population standard
deviation, count) inside it. Individual loops stay in the measurement's files.

Ad hoc parser for SOF-8050: it reads the shape UTK's afm-lib writes and nothing else.
"""
import argparse, ast, json, math, re, statistics, struct
from datetime import datetime, timezone
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
INSTRUMENT_NAME = "asylum-spm"  # the standata application whose workflow this run records
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
    images = [(f.name, f) for f in sorted(run_dir.iterdir()) if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
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
    workflow = standata_workflow(INSTRUMENT_NAME, "SS-PFM Hysteresis Loop")
    unit = unit_id(workflow)
    measurement_set = {"name": run_name, "entitySetType": "ordered",
                       "metadata": {"session": session, "recipe": recipe, "context": recipe.get("context", ""),
                                    "loop_settings": recipe["per_site"][0]["loop_settings"],
                                    "sites": list(samples), "common": common, "registration": reg}}
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
        (properties.append((label, unit, prop, 0)) if prop else skipped.append(label))
    return {"physicalId": physical_id, "run": run_name, "sample_set": sample_set, "images": images, "samples": samples,
            "measurement_set": measurement_set, "measurements": measurements, "files": files, "set_files": [],
            "records": records, "properties": properties, "skipped": skipped}



def same_axis(candidate, reference, tolerance=1e-9):
    """Whether two bias axes are the same sweep: equal length and equal voltages within tolerance."""
    return len(candidate) == len(reference) and all(
        abs(a - b) <= tolerance + 1e-6 * abs(b) for a, b in zip(candidate, reference))


def main():
    """Read a UTK run folder and write its run document."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--physical-id", required=True, help="the identifier written on the physical piece, e.g. PDAC_COM5_01448")
    ap.add_argument("--out", default="parsed", help="directory for the run document and the records cut from the run (default: parsed/)")
    ap.add_argument("--limit-records", type=int, help="trial: only the first N records and the samples they belong to")
    ap.add_argument("--deposition", help="NLR HTEM record (json) kept in the run's sample set metadata")
    ap.add_argument("--instrument", default="asylum-afm", help="identity of the machine the run was measured on (the run folder does not record it)")
    ap.add_argument("--emit-example", help="write the property with the most loops to this path — the ESSE example")
    a = ap.parse_args()

    parsed = parse(a.run_dir, a.physical_id, a.limit_records, a.deposition, a.instrument)
    files = sum(len(v) for v in parsed["files"].values())
    print(f"{parsed['physicalId']}: {len(parsed['samples'])} samples · run {parsed['run']}: "
          f"{len(parsed['measurements'])} measurements · {len(parsed['records'])} records -> {files} files · "
          f"{len(parsed['properties'])} samples with a combined loop"
          + (f" · no curves: {len(parsed['skipped'])} samples" if parsed["skipped"] else ""))
    if a.emit_example and parsed["properties"]:
        label, _, prop, _rep = max(parsed["properties"], key=lambda t: t[2]["parameters"]["off"].get("imprint", {}).get("count", 0))
        Path(a.emit_example).write_text(json.dumps(dict(prop, **thinned_curves(prop)), indent=4) + "\n")
        print(f"example written from sample {label} -> {a.emit_example}")
    print("run document:", serialize(parsed, a.out))


if __name__ == "__main__":
    main()
