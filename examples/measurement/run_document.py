"""The run document: what a parser writes and the uploader takes.

One JSON file per run, beside the files it names. Everything instrument-specific has already happened by the
time it exists — reading the lab's delivery is `parse_utk.py` / `parse_nlr.py`, uploading it is `upload_run.py`,
and neither knows anything about the other.

    {
      "physicalId":      "PDAC_COM5_01448",          the identifier written on the physical piece
      "run":             "com5_1448_xrf_grid XRF",   names the measurement set
      "sample_set":      {name, entitySetType, metadata},
      "samples":         {label: sample document},
      "measurement_set": {name, entitySetType, metadata},
      "measurements":    {label: measurement document},   _sample is filled in at upload
      "properties":      [[label, unitId, property document, repetition]],
      "set_files":       [[name, path]],             the set's own files: a grid, a photograph of the piece
      "files":           {label: [[name, path]]},    one measurement's files; the name's first segment is its group
      "skipped":         [label]                     informational: samples the run produced no property for
    }

Paths are relative to the document, so a run folder moves as a whole. A parser that derives a file (a record
JSON it cut from a larger one) writes it here too — `serialize` takes text in place of a path and stores it.
"""
import json, os
from pathlib import Path


def serialize(parsed, out_dir, name="run.json"):
    """The parsed run as a document on disk. Text payloads are written out; Paths are recorded relative to it."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def store(prefix, entries):
        out = []
        for file_name, payload in entries:
            if isinstance(payload, Path):
                out.append([file_name, relative(payload, out_dir)])
            else:  # derived text: this document owns it
                target = out_dir / "files" / prefix / file_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(payload)
                out.append([file_name, relative(target, out_dir)])
        return out

    document = {k: v for k, v in parsed.items() if k not in ("files", "set_files", "images", "measurements")}
    document["measurements"] = {label: {k: v for k, v in m.items() if k != "_records"}
                                for label, m in parsed["measurements"].items()}
    document["records_by_sample"] = {label: m["_records"] for label, m in parsed["measurements"].items() if m.get("_records")}
    document["set_files"] = store("set", list(parsed.get("set_files", [])) + list(parsed.get("images", [])))
    document["files"] = {label: store(label, entries) for label, entries in parsed.get("files", {}).items()}
    document["properties"] = [list(p) for p in parsed.get("properties", [])]
    path = out_dir / name
    path.write_text(json.dumps(document, indent=1) + "\n")
    return path


def relative(path, out_dir):
    """`path` as the document will name it: relative when it can be, absolute when it lives elsewhere."""
    path, out_dir = Path(path).resolve(), Path(out_dir).resolve()
    try:
        return path.relative_to(out_dir).as_posix()
    except ValueError:
        return os.path.relpath(path, out_dir)


def load(path):
    """A run document with its file paths resolved against its own location."""
    path = Path(path)
    document = json.loads(path.read_text())
    resolve = lambda entries: [(name, (path.parent / file_path).resolve()) for name, file_path in entries]
    document["set_files"] = resolve(document.get("set_files", []))
    document["files"] = {label: resolve(entries) for label, entries in document.get("files", {}).items()}
    document["properties"] = [tuple(p) for p in document.get("properties", [])]
    return document
