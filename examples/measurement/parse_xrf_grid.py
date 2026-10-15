"""Writes the folder mat3ra-upload reads from NLR's XRF grid: one measurement per site, the table in its files."""

import argparse
import csv
import json
import shutil
from pathlib import Path


def main():
    """Writes set.json, workflow.json and, per site, measurements/<site>.json and files/<site>/ into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grid", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    workflow_name = json.loads(arguments.workflow.read_text())["name"]

    (arguments.out_folder / "measurements").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arguments.workflow, arguments.out_folder / "workflow.json")
    set_document = {"name": arguments.grid.stem, "description": "", "metadata": {}}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    rows = list(csv.DictReader(arguments.grid.read_text().splitlines(), delimiter="\t"))
    for row in rows:
        label = f"r{row['Row']}c{row['Column']}"
        position = {"coordinates": [float(row["x_mm"]), float(row["y_mm"])], "units": "mm"}
        measurement = {
            "name": f"{arguments.grid.stem} {label}",
            "description": f"{workflow_name} at site {label}",
            "status": "finished",
            "setup": {"instrument": {}},
            "sample": {"name": label, "metadata": {"position": position}},
        }
        (arguments.out_folder / "measurements" / f"{label}.json").write_text(json.dumps(measurement, indent=4))
        (arguments.out_folder / "files" / label).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(arguments.grid, arguments.out_folder / "files" / label / arguments.grid.name)
    print(f"{len(rows)} measurements in {arguments.out_folder}")


if __name__ == "__main__":
    main()
