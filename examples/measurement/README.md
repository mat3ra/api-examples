# Uploading measurements

Requires Python 3.10+, git and git-lfs with `git lfs install` run once.

    pip install "mat3ra-parsers[alphafilm] @ git+https://github.com/mat3ra/parsers.git@alphafilm"
    mat3ra-auth alphafilm.mat3ra.com
    mat3ra-parse asylum-spm RUN upload
    mat3ra-upload WAFER_SET_NAME upload

| Instrument | RUN |
|---|---|
| `asylum-spm` | an Asylum Research run folder (`summary.json`, `loops/<point>/*.npy`) |
| `xrf-instrument` | an XRF grid table, one row per site |
| `dc-iv-instrument` | a folder with `IV_Volts.txt` and `IV_Amps.txt` |

## Adding an instrument

- [mat3ra/fixtures](https://github.com/mat3ra/fixtures/tree/alphafilm): an example run and its workflow in
  `data/instruments/<instrument>/<version>/case-NNN/`, listed in the manifests.
- [mat3ra/parsers](https://github.com/mat3ra/parsers/tree/alphafilm): the parser in
  `src/py/mat3ra/parsers/instruments/<instrument>/parser.py` and its line in `factory.py`, keyed `instruments.<instrument>`.
- [mat3ra/esse](https://github.com/mat3ra/esse): a schema for a new property, or the experimental workflow schema.
