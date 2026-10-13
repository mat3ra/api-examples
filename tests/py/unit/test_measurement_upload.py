import sys
from pathlib import Path
from types import SimpleNamespace

REPOSITORY_PATH = Path(__file__).parents[3]
sys.path.insert(0, str(REPOSITORY_PATH / "examples" / "measurement"))

import upload  # noqa: E402

FIXTURE_FOLDER = REPOSITORY_PATH / "tests" / "fixtures" / "measurement_set"
LIBRARY = {"_id": "library", "name": "PDAC_COM5_01448", "isEntitySet": True}
SAMPLE_OUTSIDE_LIBRARY = {"_id": "outside", "name": "PDAC_COM5_01448 r0c00"}
FIRST_RUN_COUNTS = {"measurement sets": {"created": 1}, "samples": {"created": 2}, "measurements": {"created": 2}}
SECOND_RUN_COUNTS = {
    "measurement sets": {"already present": 1},
    "samples": {"already present": 2},
    "measurements": {"already present": 2},
}
MEASUREMENTS_IN_SET = [("samples-2", "workflow"), ("samples-3", "workflow")]
CREATED_SAMPLE_WITH_DETAILS = {
    "_id": "samples-3",
    "name": "PDAC_COM5_01448 r1c1",
    "metadata": {"position": {"coordinates": [5.4000001, 6.6500001], "units": "mm"}},
    "inSet._id": "library",
}


class FakeEndpoint:
    def __init__(self, name, records):
        self.name = name
        self.records = records

    def list(self, query):
        return [record for record in self.records if all(record.get(key) == value for key, value in query.items())]

    def create(self, config):
        record = {**config, "_id": f"{self.name}-{len(self.records)}"}
        self.records.append(record)
        return record

    def create_set(self, config):
        return self.create({**config, "isEntitySet": True})

    def move_to_set(self, entity_id, old_set_id, new_set_id):
        next(record for record in self.records if record["_id"] == entity_id)["inSet._id"] = new_set_id


def test_upload():
    samples = FakeEndpoint("samples", [LIBRARY, SAMPLE_OUTSIDE_LIBRARY])
    client = SimpleNamespace(samples=samples, measurements=FakeEndpoint("measurements", []))

    assert upload.upload(client, LIBRARY["name"], FIXTURE_FOLDER) == FIRST_RUN_COUNTS
    assert upload.upload(client, LIBRARY["name"], FIXTURE_FOLDER) == SECOND_RUN_COUNTS
    assert len(client.samples.records) == 4
    assert client.samples.records[3] == CREATED_SAMPLE_WITH_DETAILS
    assert len(client.measurements.records) == 3
    measurements = client.measurements.list({"inSet._id": "measurements-0"})
    assert [(measurement["_sample"]["_id"], measurement["workflow"]["name"]) for measurement in measurements] == (
        MEASUREMENTS_IN_SET
    )
