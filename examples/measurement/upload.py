"""Uploads a folder of measurements as one measurement set, their samples into a sample set, and their properties."""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from mat3ra.api_client import APIClient
from mat3ra.api_client.constants import ACCOUNT_ID_ENV_VAR, AUTH_TOKEN_ENV_VAR

from auth import CREDENTIALS_FILE_PATH


def load_credentials():
    """Returns the account id and API token from the environment, else from the file auth.py wrote."""
    if os.environ.get(ACCOUNT_ID_ENV_VAR) and os.environ.get(AUTH_TOKEN_ENV_VAR):
        credentials = os.environ
    elif os.path.exists(CREDENTIALS_FILE_PATH):
        credentials = json.loads(Path(CREDENTIALS_FILE_PATH).read_text())
    else:
        sys.exit("No API credentials: run `python auth.py`, or set ACCOUNT_ID and AUTH_TOKEN.")
    return credentials[ACCOUNT_ID_ENV_VAR], credentials[AUTH_TOKEN_ENV_VAR]


def find_or_create_in_set(endpoint, config, set_id, counts):
    """Returns the entity named as in `config` directly inside the set, creating it there when missing."""
    found = endpoint.list({"name": config["name"], "inSet._id": set_id})
    counts[endpoint.name]["already present" if found else "created"] += 1
    if found:
        return found[0]
    entity = endpoint.create(config)
    endpoint.move_to_set(entity["_id"], None, set_id)
    return entity


def upload(client, sample_set_name, folder):
    """Uploads the folder and returns, per kind, how many records were created and how many were already present."""
    sample_sets = client.samples.list({"isEntitySet": True, "name": sample_set_name})
    if len(sample_sets) != 1:
        sys.exit(
            f'Found {len(sample_sets)} sample sets named "{sample_set_name}", expected one: create it in the web app.'
        )
    set_config = json.loads((folder / "set.json").read_text())
    workflow = json.loads((folder / "workflow.json").read_text())
    counts = defaultdict(Counter)

    measurement_sets = client.measurements.list({"isEntitySet": True, "name": set_config["name"]})
    counts["measurement sets"]["already present" if measurement_sets else "created"] += 1
    measurement_set = measurement_sets[0] if measurement_sets else client.measurements.create_set(set_config)

    for path in sorted((folder / "measurements").glob("*.json")):
        measurement = json.loads(path.read_text())
        sample_entry = measurement.pop("sample")
        sample_config = {"name": sample_entry} if isinstance(sample_entry, str) else sample_entry
        sample = find_or_create_in_set(client.samples, sample_config, sample_sets[0]["_id"], counts)
        config = {**measurement, "_sample": {"_id": sample["_id"]}, "workflow": workflow}
        measurement_entity = find_or_create_in_set(client.measurements, config, measurement_set["_id"], counts)
        property_path = folder / "properties" / path.name
        if not property_path.exists():
            continue
        property_document = json.loads(property_path.read_text())
        query = {"source.info.origin._id": measurement_entity["_id"], "data.name": property_document["name"]}
        found = client.properties.list(query)
        counts["properties"]["already present" if found else "created"] += 1
        if not found:
            origin = {"_id": measurement_entity["_id"], "cls": "Measurement"}
            subject = {"_id": sample["_id"], "cls": "Sample"}
            unit_id = workflow["subworkflows"][0]["units"][0]["flowchartId"]
            source = {"type": "external", "info": {"origin": origin, "subject": subject, "unitId": unit_id}}
            client.properties.create({"data": property_document, "source": source, "exabyteId": []})
    return counts


def main():
    """Parses the two arguments, authenticates, uploads, and prints the counts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_set_name")
    parser.add_argument("folder", type=Path)
    arguments = parser.parse_args()
    account_id, auth_token = load_credentials()
    client = APIClient.authenticate(account_id=account_id, auth_token=auth_token)
    for kind, kind_counts in upload(client, arguments.sample_set_name, arguments.folder).items():
        print(f"{kind}: {kind_counts['created']} created, {kind_counts['already present']} already present")


if __name__ == "__main__":
    main()
