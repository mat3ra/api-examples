# Measurement upload

`upload.py` puts a folder of measurements into the platform as one measurement set; their samples go into a sample
set created in the web app.

## Install

    pip install "mat3ra-notebooks-utils[api]"
    pip install "git+https://github.com/mat3ra/api-client.git@feature/SOF-8081"

For a platform other than `platform.mat3ra.com`, set `API_HOST` (and `API_PORT`, `API_SECURE`).

## Sign in once

    python auth.py

Prints a sign-in link and code. After you confirm, it stores your account id and an API token, which does not expire,
in `~/.mat3ra/api_token_cache.json`. Setting `ACCOUNT_ID` and `AUTH_TOKEN` in the environment replaces this step.

## Upload

    python upload.py <SAMPLE_SET_NAME> <FOLDER>

Samples are matched and created directly in the named set, so name the set the samples live in.
Measurements are found by name inside the measurement set. Running it again creates nothing new.

## Folder

    <FOLDER>/
        set.json            name, description, metadata of the measurement set
        workflow.json       the workflow of every measurement
        measurements/*.json name, description, metadata, setup, status, and sample: the sample's name

Example: `tests/fixtures/measurement_set/`.
