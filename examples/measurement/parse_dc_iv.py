"""Writes the folder mat3ra-upload reads from NLR's DC I-V data: IV_Volts.txt and IV_Amps.txt, one sweep per row."""

import argparse
import json
import shutil
from pathlib import Path


def main():
    """Writes set.json, workflow.json and measurements/row<N>.json into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_folder", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    set_name = arguments.data_folder.name

    (arguments.out_folder / "measurements").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arguments.workflow, arguments.out_folder / "workflow.json")
    set_document = {"name": set_name, "description": "", "metadata": {}}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    voltage_lines = (arguments.data_folder / "IV_Volts.txt").read_text().splitlines()[1:]
    current_lines = (arguments.data_folder / "IV_Amps.txt").read_text().splitlines()[1:]
    for row_number, (voltage_line, current_line) in enumerate(zip(voltage_lines, current_lines), start=1):
        label = f"row{row_number}"
        measurement = {
            "name": f"{set_name} {label}",
            "status": "finished",
            "setup": {"instrument": {}},
            "sample": {"name": label},
            "metadata": {
                "voltage_v": [float(value) for value in voltage_line.split("\t")],
                "current_a": [float(value) for value in current_line.split("\t")],
            },
        }
        (arguments.out_folder / "measurements" / f"{label}.json").write_text(json.dumps(measurement, indent=4))
    print(f"{len(voltage_lines)} measurements in {arguments.out_folder}")


if __name__ == "__main__":
    main()
