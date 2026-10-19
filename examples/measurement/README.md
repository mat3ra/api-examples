# Measurement folder

Sign in once and upload with api-client's commands; `mat3ra-upload` puts a folder below in as one measurement set:

    git clone -b feature/SOF-8081 https://github.com/mat3ra/api-examples.git
    cd api-examples
    pip install -e ".[measurement]"
    mat3ra-auth alphafilm.mat3ra.com
    python examples/measurement/parse_spm_hysteresis.py RUN_FOLDER tests/fixtures/measurement_set/workflow.json FOLDER
    mat3ra-upload WAFER_SET_NAME FOLDER

## Folder

    <FOLDER>/
        set.json               name, description, metadata of the measurement set
        <measurement>/         one folder per measurement, any name (the sample's name in these parsers)
            measurement.json   name, description, status, setup, workflow, sample, properties, metadata
            files/...          optional, the measurement's files as delivered

`sample` is `{name, description, metadata}` (description and metadata optional) or just the name.

## From an Asylum Research run

    python examples/measurement/parse_spm_hysteresis.py <RUN_FOLDER> tests/fixtures/measurement_set/workflow.json <FOLDER>

`parse_spm_hysteresis.py` reads the run as delivered, `summary.json` and `loops/<point>/{bias,X,Y}_{on,off}.npy`, and
writes the folder above: one measurement per pad with the instrument, the run's session and the instrument settings as
its setup, the pad as its sample with the stage position in metadata, and a `hysteresis_loop` property for every pad
whose loops share one bias axis. It is the example of what a run must become; another instrument needs its own parser
writing the same folder.

- `python examples/measurement/parse_xrf_grid.py <XRF_GRID_TXT> tests/fixtures/xrf_grid/workflow.json <FOLDER>`: one
  measurement per site of NLR's XRF grid, the delivered table under `<measurement>/files/`.
- `python examples/measurement/parse_dc_iv.py <IV_FOLDER> tests/fixtures/dc_iv/workflow.json <FOLDER>`: one measurement
  per row of NLR's I-V sweeps, the delivered `IV_Volts.txt` and `IV_Amps.txt` under `<measurement>/files/`.
