# Measurement folder

Sign in once and upload with api-client's commands; `mat3ra-upload` puts a folder below in as one measurement set:

    pip install "git+https://github.com/mat3ra/api-client.git@e488bb8"
    mat3ra-auth alphafilm.mat3ra.com
    mat3ra-upload NAME FOLDER

## Folder

    <FOLDER>/
        set.json            name, description, metadata of the measurement set
        workflow.json       the workflow of every measurement
        measurements/*.json name, description, metadata, setup, status, and sample
        properties/*.json   optional: a property of the measurement with the same file name
        files/<label>/      optional: the files of measurements/<label>.json under their run paths, e.g. loops/<point>/

`sample` is `{name, description, metadata}` (description and metadata optional) or just the name.

## From an Asylum Research run

    pip install numpy
    python parse_spm_hysteresis.py <RUN_FOLDER> <WORKFLOW_JSON> <FOLDER>

`parse_spm_hysteresis.py` reads the run as delivered, `summary.json` and `loops/<point>/{bias,X,Y}_{on,off}.npy`, and
writes the folder above: one measurement per pad with the instrument, the run's session and the instrument settings as
its setup, the pad as its sample with the stage position in metadata, and a `hysteresis_loop` property for every pad
whose loops share one bias axis. It is the example of what a run must become; another instrument needs its own parser
writing the same folder.

- `python parse_xrf_grid.py <XRF_GRID_TXT> <WORKFLOW_JSON> <FOLDER>`: one measurement per site of NLR's XRF grid, the
  delivered table under `files/<label>/`.
- `python parse_dc_iv.py <IV_FOLDER> <WORKFLOW_JSON> <FOLDER>`: one measurement per row of NLR's I-V sweeps, the
  delivered `IV_Volts.txt` and `IV_Amps.txt` under `files/<label>/`.
