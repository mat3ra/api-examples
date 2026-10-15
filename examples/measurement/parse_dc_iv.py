"""Writes the folder mat3ra-upload reads from NLR's DC I-V data: one measurement per row, both tables in its files."""

import argparse
import json
import shutil
from pathlib import Path


def main():
    """Writes set.json, workflow.json and, per row, measurements/row<N>.json and files/row<N>/ into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_folder", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    set_name = arguments.data_folder.name
    workflow_name = json.loads(arguments.workflow.read_text())["name"]

    (arguments.out_folder / "measurements").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arguments.workflow, arguments.out_folder / "workflow.json")
    set_document = {"name": set_name, "description": "", "metadata": {}}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    voltage_lines = (arguments.data_folder / "IV_Volts.txt").read_text().splitlines()[1:]
    for row_number in range(1, len(voltage_lines) + 1):
        label = f"row{row_number}"
        measurement = {
            "name": f"{set_name} {label}",
            "description": f"{workflow_name} at {label}",
            "status": "finished",
            "setup": {"instrument": {}},
            "sample": {"name": label},
        }
        (arguments.out_folder / "measurements" / f"{label}.json").write_text(json.dumps(measurement, indent=4))
        (arguments.out_folder / "files" / label).mkdir(parents=True, exist_ok=True)
        for file_name in ("IV_Volts.txt", "IV_Amps.txt"):
            shutil.copyfile(arguments.data_folder / file_name, arguments.out_folder / "files" / label / file_name)
    print(f"{len(voltage_lines)} measurements in {arguments.out_folder}")


if __name__ == "__main__":
    main()
