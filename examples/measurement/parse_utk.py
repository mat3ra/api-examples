"""Writes the folder upload.py reads from an Asylum Research run folder: summary.json and loops/<point>/*.npy."""

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path, PureWindowsPath

import numpy


def combined(loop_parameters, key):
    """Mean, population standard deviation and count of one parameter over the loops that carry it."""
    values = [parameters[key] for parameters in loop_parameters if parameters[key] is not None]
    return {"value": float(numpy.mean(values)), "standardDeviation": float(numpy.std(values)), "count": len(values)}


def hysteresis_loop(run_folder, entries):
    """The pad's hysteresis_loop property, or None unless its loops cover both conditions on one bias axis."""
    biases, responses, parameters = [], {"on": [], "off": []}, {}
    for condition in responses:
        loop_parameters = [entry["loop_params"][f"{condition}_field"] for entry in entries]
        for entry, loop in zip(entries, loop_parameters):
            loop_folder = run_folder / "loops" / PureWindowsPath(entry["segmentation"]["bias_on_path"]).parent.name
            paths = [loop_folder / f"{channel}_{condition}.npy" for channel in ("bias", "X", "Y")]
            if not all(path.exists() for path in paths):
                continue
            bias, x, y = (numpy.load(path).astype(float) for path in paths)
            angle = numpy.radians(loop["phase_offset_deg"])
            biases.append(bias)
            responses[condition].append(x * numpy.cos(angle) + y * numpy.sin(angle))
        parameters[condition] = {
            "imprint": combined(loop_parameters, "imprint_v"),
            "coerciveVoltage": {
                "rising": combined(loop_parameters, "v_c_rising"),
                "falling": combined(loop_parameters, "v_c_falling"),
            },
            "loopWidth": combined(loop_parameters, "loop_width_v"),
            "loopHeight": combined(loop_parameters, "loop_height_m"),
            "remanentResponse": {
                "rising": combined(loop_parameters, "remnant_rising_m"),
                "falling": combined(loop_parameters, "remnant_falling_m"),
            },
        }
    if not responses["on"] or not responses["off"] or any(not numpy.array_equal(bias, biases[0]) for bias in biases):
        return None
    return {
        "name": "hysteresis_loop",
        "legend": ["on", "off"],
        "xAxis": {"label": "bias", "units": "V"},
        "yAxis": {"label": "response", "units": "m"},
        "xDataArray": biases[0].tolist(),
        "yDataSeries": [numpy.mean(responses[condition], axis=0).tolist() for condition in ("on", "off")],
        "parameters": parameters,
    }


def main():
    """Writes set.json, workflow.json, measurements/<pad>.json and properties/<pad>.json into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    summary = json.loads((arguments.run_folder / "summary.json").read_text())
    run_name = summary["run"]["name"]

    (arguments.out_folder / "measurements").mkdir(parents=True, exist_ok=True)
    (arguments.out_folder / "properties").mkdir(exist_ok=True)
    shutil.copyfile(arguments.workflow, arguments.out_folder / "workflow.json")
    set_metadata = {key: value for key, value in summary.items() if key != "measurements"}
    set_document = {"name": run_name, "description": "", "metadata": set_metadata}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    entries_by_pad = defaultdict(list)
    for entry in summary["measurements"]:
        entries_by_pad[entry["labels"]["site_label"]].append(entry)
    properties_count = 0
    for label, entries in entries_by_pad.items():
        measurement = {
            "name": f"{run_name} {label}",
            "status": "finished",
            "setup": {"instrument": {"name": "Asylum Research"}, "settings": summary["recipe"]["per_site"]},
            "sample": {"name": label, "metadata": {"position": entries[0]["achieved"]["stage_position"]}},
            "metadata": {
                "measurements": [
                    {
                        **entry,
                        "achieved": {key: value for key, value in entry["achieved"].items() if key != "stage_position"},
                    }
                    for entry in entries
                ]
            },
        }
        (arguments.out_folder / "measurements" / f"{label}.json").write_text(json.dumps(measurement, indent=4))
        property_document = hysteresis_loop(arguments.run_folder, entries)
        if property_document:
            (arguments.out_folder / "properties" / f"{label}.json").write_text(json.dumps(property_document, indent=4))
            properties_count += 1
    print(f"{len(entries_by_pad)} measurements, {properties_count} with a hysteresis loop, in {arguments.out_folder}")


if __name__ == "__main__":
    main()
