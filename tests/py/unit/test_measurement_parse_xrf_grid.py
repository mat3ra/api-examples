import json
import subprocess
import sys
from pathlib import Path

from mat3ra.esse import ESSE

REPOSITORY_PATH = Path(__file__).parents[3]
PARSER_PATH = REPOSITORY_PATH / "examples" / "measurement" / "parse_xrf_grid.py"
GRID_PATH = REPOSITORY_PATH / "tests" / "fixtures" / "xrf_grid" / "com5_1448_xrf_grid.txt"
WORKFLOW_PATH = REPOSITORY_PATH / "tests" / "fixtures" / "xrf_grid" / "workflow.json"
EXPECTED_MEASUREMENT_NAMES = ["com5_1448_xrf_grid r1c1", "com5_1448_xrf_grid r1c2"]
EXPECTED_FIRST_SITE = {
    "name": "com5_1448_xrf_grid r1c1",
    "description": "XRF Grid Map at site r1c1",
    "status": "finished",
    "setup": {"instrument": {}},
    "sample": {"name": "r1c1", "metadata": {"position": {"coordinates": [5.4000001, 6.6500001], "units": "mm"}}},
}
EXPECTED_FILES = {"r1c1/files/com5_1448_xrf_grid.txt": GRID_PATH, "r1c2/files/com5_1448_xrf_grid.txt": GRID_PATH}


def test_parse_xrf_grid(tmp_path):
    esse = ESSE()
    subprocess.run([sys.executable, PARSER_PATH, GRID_PATH, WORKFLOW_PATH, tmp_path], check=True)
    workflow = json.loads(WORKFLOW_PATH.read_text())
    measurements = [json.loads(path.read_text()) for path in sorted(tmp_path.glob("*/measurement.json"))]

    assert [measurement["name"] for measurement in measurements] == EXPECTED_MEASUREMENT_NAMES
    assert measurements[0] == {**EXPECTED_FIRST_SITE, "workflow": workflow}
    files = {path.relative_to(tmp_path).as_posix(): path.read_bytes() for path in tmp_path.glob("*/files/*")}
    assert files == {name: path.read_bytes() for name, path in EXPECTED_FILES.items()}
    for measurement in measurements:
        measurement.pop("sample")
        measurement_document = {**measurement, "_sample": {"_id": "sample"}}
        esse.validate(measurement_document, esse.get_schema_by_id("measurement"))
