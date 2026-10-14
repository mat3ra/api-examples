import json
import subprocess
import sys
from pathlib import Path

from mat3ra.esse import ESSE

REPOSITORY_PATH = Path(__file__).parents[3]
PARSER_PATH = REPOSITORY_PATH / "examples" / "measurement" / "parse_dc_iv.py"
DATA_FOLDER = REPOSITORY_PATH / "tests" / "fixtures" / "dc_iv" / "1448 DC IV data"
WORKFLOW_PATH = REPOSITORY_PATH / "tests" / "fixtures" / "dc_iv" / "workflow.json"
EXPECTED_MEASUREMENT_NAMES = ["1448 DC IV data row1", "1448 DC IV data row2"]


def test_parse_dc_iv(tmp_path):
    esse = ESSE()
    subprocess.run([sys.executable, PARSER_PATH, DATA_FOLDER, WORKFLOW_PATH, tmp_path], check=True)
    workflow = json.loads((tmp_path / "workflow.json").read_text())
    measurements = [json.loads(path.read_text()) for path in sorted((tmp_path / "measurements").glob("*.json"))]

    assert [measurement["name"] for measurement in measurements] == EXPECTED_MEASUREMENT_NAMES
    for measurement in measurements:
        measurement.pop("sample")
        measurement_document = {**measurement, "_sample": {"_id": "sample"}, "workflow": workflow}
        esse.validate(measurement_document, esse.get_schema_by_id("measurement"))
