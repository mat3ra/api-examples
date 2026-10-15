"""Writes the folder mat3ra-upload reads from NLR's XRF grid: a tab-separated table, one row per site."""

import argparse
import csv
import json
import shutil
from pathlib import Path


def main():
    """Writes set.json and, per site, <site>/measurement.json and <site>/files/ into the out folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grid", type=Path)
    parser.add_argument("workflow", type=Path)
    parser.add_argument("out_folder", type=Path)
    arguments = parser.parse_args()
    workflow = json.loads(arguments.workflow.read_text())

    arguments.out_folder.mkdir(parents=True, exist_ok=True)
    set_document = {"name": arguments.grid.stem, "description": "", "metadata": {}}
    (arguments.out_folder / "set.json").write_text(json.dumps(set_document, indent=4))

    rows = list(csv.DictReader(arguments.grid.read_text().splitlines(), delimiter="\t"))
    for row in rows:
        label = f"r{row['Row']}c{row['Column']}"
        position = {"coordinates": [float(row["x_mm"]), float(row["y_mm"])], "units": "mm"}
        measurement = {
            "name": f"{arguments.grid.stem} {label}",
            "description": f"{workflow['name']} at site {label}",
            "status": "finished",
            "setup": {"instrument": {}},
            "workflow": workflow,
            "sample": {"name": label, "metadata": {"position": position}},
        }
        (arguments.out_folder / label / "files").mkdir(parents=True, exist_ok=True)
        (arguments.out_folder / label / "measurement.json").write_text(json.dumps(measurement, indent=4))
        shutil.copyfile(arguments.grid, arguments.out_folder / label / "files" / arguments.grid.name)
    print(f"{len(rows)} measurements in {arguments.out_folder}")


if __name__ == "__main__":
    main()
