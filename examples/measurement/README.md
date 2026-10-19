# Uploading measurements

Requires Python 3.10+, git and git-lfs.

    git clone -b alphafilm https://github.com/mat3ra/api-examples.git
    cd api-examples
    pip install -e ".[measurement]"

Run the notebook, which signs in, parses a run and uploads it:

    jupyter lab examples/measurement/upload_measurements.ipynb

or, with a folder already in the upload format:

    mat3ra-auth alphafilm.mat3ra.com
    mat3ra-upload <wafer set name> <folder>

The folder is described in
[api-client's README](https://github.com/mat3ra/api-client/tree/alphafilm#uploading-measurements).

## Adding an application

- [mat3ra/fixtures](https://github.com/mat3ra/fixtures/tree/alphafilm): an example run and its workflow in
  `data/applications/<application>/<version>/case-NNN/`, listed in the manifests.
- [mat3ra/parsers](https://github.com/mat3ra/parsers/tree/alphafilm): the parser in
  `applications/<application>/<executable>/parser.py` and its line in `factory.py`.
- [mat3ra/esse](https://github.com/mat3ra/esse): a schema for a new property or workflow.
