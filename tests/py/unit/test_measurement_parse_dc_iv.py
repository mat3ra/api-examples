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
EXPECTED_FIRST_ROW = {
    "name": "1448 DC IV data row1",
    "description": "DC I-V Sweep at row1",
    "status": "finished",
    "setup": {"instrument": {}},
    "sample": {"name": "row1"},
}
EXPECTED_FILES = {
    "files/row1/IV_Volts.txt": DATA_FOLDER / "IV_Volts.txt",
    "files/row1/IV_Amps.txt": DATA_FOLDER / "IV_Amps.txt",
    "files/row2/IV_Volts.txt": DATA_FOLDER / "IV_Volts.txt",
    "files/row2/IV_Amps.txt": DATA_FOLDER / "IV_Amps.txt",
}


def test_parse_dc_iv(tmp_path):
    esse = ESSE()
    subprocess.run([sys.executable, PARSER_PATH, DATA_FOLDER, WORKFLOW_PATH, tmp_path], check=True)
    workflow = json.loads((tmp_path / "workflow.json").read_text())
    measurements = [json.loads(path.read_text()) for path in sorted((tmp_path / "measurements").glob("*.json"))]

    assert [measurement["name"] for measurement in measurements] == EXPECTED_MEASUREMENT_NAMES
    assert measurements[0] == EXPECTED_FIRST_ROW
    files = {path.relative_to(tmp_path).as_posix(): path.read_bytes() for path in tmp_path.glob("files/*/*")}
    assert files == {name: path.read_bytes() for name, path in EXPECTED_FILES.items()}
    for measurement in measurements:
        measurement.pop("sample")
        measurement_document = {**measurement, "_sample": {"_id": "sample"}, "workflow": workflow}
        esse.validate(measurement_document, esse.get_schema_by_id("measurement"))
