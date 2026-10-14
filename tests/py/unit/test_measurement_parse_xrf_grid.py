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


def test_parse_xrf_grid(tmp_path):
    esse = ESSE()
    subprocess.run([sys.executable, PARSER_PATH, GRID_PATH, WORKFLOW_PATH, tmp_path], check=True)
    workflow = json.loads((tmp_path / "workflow.json").read_text())
    measurements = [json.loads(path.read_text()) for path in sorted((tmp_path / "measurements").glob("*.json"))]

    assert [measurement["name"] for measurement in measurements] == EXPECTED_MEASUREMENT_NAMES
    for measurement in measurements:
        measurement.pop("sample")
        measurement_document = {**measurement, "_sample": {"_id": "sample"}, "workflow": workflow}
        esse.validate(measurement_document, esse.get_schema_by_id("measurement"))
