# Uploading measurements

Requires Python 3.10+, git and git-lfs.

    git clone -b alphafilm https://github.com/mat3ra/api-examples.git
    cd api-examples
    pip install -e ".[measurement]"
    mat3ra-auth alphafilm.mat3ra.com
    mat3ra-parse asylum-spm RUN upload
    mat3ra-upload WAFER_SET_NAME upload

| Application | RUN |
|---|---|
| `asylum-spm` | an Asylum Research run folder (`summary.json`, `loops/<point>/*.npy`) |
| `xrf-instrument` | an XRF grid table, one row per site |
| `dc-iv-instrument` | a folder with `IV_Volts.txt` and `IV_Amps.txt` |

[upload_measurements.ipynb](upload_measurements.ipynb) runs the same commands.

The folder is described in
[api-client's README](https://github.com/mat3ra/api-client/tree/alphafilm#uploading-measurements).

## Adding an application

- [mat3ra/fixtures](https://github.com/mat3ra/fixtures/tree/alphafilm): an example run and its workflow in
  `data/applications/<application>/<version>/case-NNN/`, listed in the manifests.
- [mat3ra/parsers](https://github.com/mat3ra/parsers/tree/alphafilm): the parser in
  `applications/<application>/<executable>/parser.py` and its line in `factory.py`.
- [mat3ra/esse](https://github.com/mat3ra/esse): a schema for a new property or workflow.
