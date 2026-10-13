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
        measurements/*.json name, description, metadata, setup, status, and sample
        properties/*.json   optional: a property of the measurement with the same file name

`sample` is `{name, description, metadata}` (description and metadata optional) or just the name.

Example: `tests/fixtures/measurement_set/`.

## From an Asylum Research run

    pip install numpy
    python parse_utk.py <RUN_FOLDER> <WORKFLOW_JSON> <FOLDER>

`parse_utk.py` reads the run as delivered, `summary.json` and `loops/<point>/{bias,X,Y}_{on,off}.npy`, and writes the
folder above: one measurement per pad with the recipe's per-site settings as its setup, the pad as its sample with the
stage position in metadata, and a `hysteresis_loop` property for every pad whose loops share one bias axis. It is the
example of what a run must become; another instrument needs its own parser writing the same folder.
