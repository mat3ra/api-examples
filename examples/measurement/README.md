# Uploading a measurement run

Data a lab delivers becomes Samples, Measurements and Properties on the platform in two steps that stay apart:
**parse** reads one lab's delivery and writes a *run document*; **upload** takes run documents and sends them.
Nothing in the uploader knows what an instrument is, and no parser talks to the platform.

```
  delivery ──► parse_utk.py ──► run document ──► upload_run.py ──► platform
               parse_nlr.py     (parsed/*.json)
```

## Install

```bash
python -m venv venv && . venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

That file names every package and the exact source of each. Three of them are pinned to a branch: the PyPI
releases do not yet have the REST endpoints, the instrument registry entries, or the Sample and Measurement
schemas this example uses. The pins become ordinary version numbers when those branches release.

Check it worked — this must print three workflow names, not `None`:

```bash
python -c "from mat3ra.standata.workflows import WorkflowStandata as W; print([
    W.find_by_application_and_name(a, n)['name'] for a, n in
    (('asylum-spm','SS-PFM Hysteresis Loop'),('xrf-mapper','XRF Grid Map'),('probe-station','DC I-V Sweep'))])"
```

## Credentials

The uploader reads them from the environment. Either an API token from the platform's Preferences page:

```bash
export ACCOUNT_ID=... AUTH_TOKEN=...
export MAT3RA_HOST=alphafilm.mat3ra.com     # or pass --host
```

or, if you signed in through the browser, `OIDC_ACCESS_TOKEN`.

## Parse

Each parser reads one lab's delivery. Point it at the folder as delivered and give it the identifier written
on the physical piece — every Sample carries it, and it is how the piece is found again later.

```bash
# UTK: an Asylum SPM run folder (summary.json or recipe.json + records/ + loops/)
python parse_utk.py ~/data/From_UTK --physical-id PDAC_COM5_01448 --out parsed

# NLR: an XRF grid and a DC I-V sweep over the same pads
python parse_nlr.py ~/data/From_NLR --physical-id PDAC_COM5_01448 \
    --xrf-instrument bruker-m4 --iv-instrument keithley-4200 --out parsed
```

`parsed/` now holds a run document per run, plus any file a parser derived. Read it — it is the whole upload,
in JSON, before anything is sent. `run_document.py` states the shape.

## Upload

```bash
python upload_run.py parsed/*.json --account <your account slug> --files records
```

- `--files` picks which file groups go up: `records` (the per-measurement JSONs, the delivered tables, the
  photographs) and `loops` (the raw arrays and plots — thousands of files, tens of minutes). `--files` with no
  value uploads none and keeps the raw records in each measurement's metadata instead.
- `--dry-run` validates the documents against the ESSE schemas and stops.
- Re-running is safe: sets are found by name, samples and measurements by label, properties by what they belong
  to. A second pass creates nothing.

Then open the platform's Measurements tab: the run is there as a set, one measurement per sample.

## Adding a lab

Write a parser. It reads whatever that lab ships and returns the dict `run_document.py` describes — one sample
per measured position, one measurement per sample, the properties each measurement produced. Take the
measurement's workflow from standata (`standata_workflow(application, name)`); if the instrument is not in that
registry yet, add it there — `mat3ra/standata`, `assets/applications/` and `assets/workflows/` — rather than
building a workflow in Python, so the platform resolves it the same way it resolves a job's.

Nothing in `upload_run.py` changes.

## The notebooks

`upload_spm_run.ipynb` and `upload_nlr_data.ipynb` run the same three steps with the same code, for people who
would rather not use a terminal. They install the pins themselves; restart the kernel after that cell if either
package was already imported.
