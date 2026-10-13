"""Writes the folder upload.py reads from an Asylum Research run folder: summary.json and loops/<point>/*.npy."""

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path, PureWindowsPath

import numpy


def parameter_statistics(parameters_per_loop, key):
    """Mean, population standard deviation and count of one parameter over the loops that carry it."""
    values = [loop_parameters[key] for loop_parameters in parameters_per_loop if loop_parameters[key] is not None]
    return {"value": float(numpy.mean(values)), "standardDeviation": float(numpy.std(values)), "count": len(values)}


def hysteresis_loop(run_folder, entries):
    """The pad's hysteresis_loop property, None unless both conditions share a bias axis, and loops per condition."""
    biases, responses, parameters = [], {"on": [], "off": []}, {}
    for condition in responses:
        parameters_per_loop = [entry["loop_params"][f"{condition}_field"] for entry in entries]
        for entry, loop_parameters in zip(entries, parameters_per_loop):
            loop_folder = run_folder / "loops" / PureWindowsPath(entry["segmentation"]["bias_on_path"]).parent.name
            paths = [loop_folder / f"{channel}_{condition}.npy" for channel in ("bias", "X", "Y")]
            if not all(path.exists() for path in paths):
                continue
            bias, x, y = (numpy.load(path).astype(float) for path in paths)
            angle = numpy.radians(loop_parameters["phase_offset_deg"])
            biases.append(bias)
            # X and Y are the lock-in quadratures; turned by the loop's phase offset, the switching lies along one axis
            responses[condition].append(x * numpy.cos(angle) + y * numpy.sin(angle))
        parameters[condition] = {
            "imprint": parameter_statistics(parameters_per_loop, "imprint_v"),
            "coerciveVoltage": {
                "rising": parameter_statistics(parameters_per_loop, "v_c_rising"),
                "falling": parameter_statistics(parameters_per_loop, "v_c_falling"),
            },
            "loopWidth": parameter_statistics(parameters_per_loop, "loop_width_v"),
            "loopHeight": parameter_statistics(parameters_per_loop, "loop_height_m"),
            "remanentResponse": {
                "rising": parameter_statistics(parameters_per_loop, "remnant_rising_m"),
                "falling": parameter_statistics(parameters_per_loop, "remnant_falling_m"),
            },
        }
    loop_counts = {condition: len(responses[condition]) for condition in responses}
    if not responses["on"] or not responses["off"] or any(not numpy.array_equal(bias, biases[0]) for bias in biases):
        return None, loop_counts
    return {
        "name": "hysteresis_loop",
        "legend": ["on", "off"],
        "xAxis": {"label": "bias", "units": "V"},
        "yAxis": {"label": "response", "units": "m"},
        "xDataArray": biases[0].tolist(),
        "yDataSeries": [numpy.mean(responses[condition], axis=0).tolist() for condition in ("on", "off")],
        "parameters": parameters,
    }, loop_counts


def main():
    """Writes set.json, workflow.json and, per pad, measurements/, properties/ and files/ into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_folder", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    summary = json.loads((arguments.run_folder / "summary.json").read_text())
    run_name = summary["run"]["name"]
    workflow_name = json.loads(arguments.workflow.read_text())["name"]
    technique = " ".join(word if word.isupper() else word.lower() for word in workflow_name.split())

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
        property_document, loop_counts = hysteresis_loop(arguments.run_folder, entries)
        for entry in entries:
            point = PureWindowsPath(entry["segmentation"]["bias_on_path"]).parent.name
            if (arguments.run_folder / "loops" / point).is_dir():
                files_folder = arguments.out_folder / "files" / label / "loops" / point
                shutil.copytree(arguments.run_folder / "loops" / point, files_folder, dirs_exist_ok=True)
        kind = summary["recipe"]["per_site"][entries[0]["labels"]["step_index"]]["kind"]
        loop_count = sum(loop_counts.values())
        loops_per_condition = ", ".join(f"{count} {condition}-field" for condition, count in loop_counts.items())
        loops = f"{loop_count} {kind}s ({loops_per_condition})" if loop_count else f"no {kind}s"
        measurement = {
            "name": f"{run_name} {label}",
            "description": f"{technique} at site {label}, {loops}",
            "status": "finished",
            "setup": {
                "instrument": {"name": "Asylum Research"},
                "session": summary["run"],
                "settings": {
                    group: settings
                    for group, settings in entries[0]["achieved"].items()
                    if group not in ("stage_position", "probe_position")
                },
            },
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
        if property_document:
            (arguments.out_folder / "properties" / f"{label}.json").write_text(json.dumps(property_document, indent=4))
            properties_count += 1
    print(f"{len(entries_by_pad)} measurements, {properties_count} with a hysteresis loop, in {arguments.out_folder}")


if __name__ == "__main__":
    main()
