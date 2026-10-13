import json
import subprocess
import sys
from pathlib import Path

from mat3ra.esse import ESSE

REPOSITORY_PATH = Path(__file__).parents[3]
PARSER_PATH = REPOSITORY_PATH / "examples" / "measurement" / "parse_spm_hysteresis.py"
RUN_FOLDER = REPOSITORY_PATH / "tests" / "fixtures" / "asylum_run"
WORKFLOW_PATH = REPOSITORY_PATH / "tests" / "fixtures" / "measurement_set" / "workflow.json"
EXPECTED_COUNTS = {"measurements": 2, "properties": 1}
EXPECTED_DESCRIPTIONS = [
    "SS-PFM hysteresis loop at site r0c00, 16 loops (8 on-field, 8 off-field)",
    "SS-PFM hysteresis loop at site r5c05, no loops",
]
HYSTERESIS_LOOP_SCHEMA_ID = "properties-directory/non-scalar/hysteresis-loop"
HYSTERESIS_LOOP_EXAMPLE_PATH = "properties_directory/non-scalar/hysteresis_loop"


def rounded(value):
    """The value, or every number in it, at the six significant digits of the esse example."""
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rounded(item) for item in value]
    return float(f"{value:.6g}")


def points(property_document):
    """The (bias, on, off) points of a hysteresis loop, rounded."""
    return set(zip(*rounded([property_document["xDataArray"], *property_document["yDataSeries"]])))


def test_parse_spm_hysteresis(tmp_path):
    esse = ESSE()
    subprocess.run([sys.executable, PARSER_PATH, RUN_FOLDER, WORKFLOW_PATH, tmp_path], check=True)
    workflow = json.loads((tmp_path / "workflow.json").read_text())
    measurements = [json.loads(path.read_text()) for path in sorted((tmp_path / "measurements").glob("*.json"))]
    properties = [json.loads(path.read_text()) for path in sorted((tmp_path / "properties").glob("*.json"))]
    example = next(item["data"] for item in esse.wrapped_examples if item["path"] == HYSTERESIS_LOOP_EXAMPLE_PATH)

    assert {"measurements": len(measurements), "properties": len(properties)} == EXPECTED_COUNTS
    assert [measurement["description"] for measurement in measurements] == EXPECTED_DESCRIPTIONS
    for measurement in measurements:
        esse.validate(measurement.pop("sample"), esse.get_schema_by_id("sample"))
        measurement_document = {**measurement, "_sample": {"_id": "sample"}, "workflow": workflow}
        esse.validate(measurement_document, esse.get_schema_by_id("measurement"))
    esse.validate(properties[0], esse.get_schema_by_id(HYSTERESIS_LOOP_SCHEMA_ID))
    assert points(example) <= points(properties[0])
    assert rounded(properties[0]["parameters"]) == rounded(example["parameters"])
