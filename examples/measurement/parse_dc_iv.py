"""Writes the folder mat3ra-upload reads from NLR's DC I-V data: IV_Volts.txt and IV_Amps.txt, one sweep per row."""

import argparse
import json
import shutil
from pathlib import Path


def main():
    """Writes set.json and, per row, row<N>/measurement.json and row<N>/files/ into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_folder", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    set_name = arguments.data_folder.name
    workflow = json.loads(arguments.workflow.read_text())

    arguments.out_folder.mkdir(parents=True, exist_ok=True)
    set_document = {"name": set_name, "description": "", "metadata": {}}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    voltage_lines = (arguments.data_folder / "IV_Volts.txt").read_text().splitlines()[1:]
    for row_number in range(1, len(voltage_lines) + 1):
        label = f"row{row_number}"
        measurement = {
            "name": f"{set_name} {label}",
            "description": f"{workflow['name']} at {label}",
            "status": "finished",
            "setup": {"instrument": {}},
            "workflow": workflow,
            "sample": {"name": label},
        }
        (arguments.out_folder / label / "files").mkdir(parents=True, exist_ok=True)
        (arguments.out_folder / label / "measurement.json").write_text(json.dumps(measurement, indent=4))
        for file_name in ("IV_Volts.txt", "IV_Amps.txt"):
            shutil.copyfile(arguments.data_folder / file_name, arguments.out_folder / label / "files" / file_name)
    print(f"{len(voltage_lines)} measurements in {arguments.out_folder}")


if __name__ == "__main__":
    main()
