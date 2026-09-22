#!/usr/bin/env python3
"""Run documents -> the platform: the sample set, its samples, the measurement set, one measurement per sample,
the files and the properties, validated against the ESSE schemas before anything is sent.

    upload_run.py parsed/run.json --account <slug>                 # upload it
    upload_run.py parsed/*.json --account <slug> --files records loops
    upload_run.py parsed/run.json --dry-run                        # validate only

It knows nothing about any instrument. Reading a lab's delivery into a run document is a parser's job —
`parse_utk.py` for a UTK SS-PFM run, `parse_nlr.py` for NLR's delivery — and `run_document.py` states the
shape they agree on. A new lab is a new parser; nothing here changes.

Requires Python 3.9+ and `pip install mat3ra-api-client`, which talks to the platform and takes OIDC_ACCESS_TOKEN,
or ACCOUNT_ID + AUTH_TOKEN (an API token from Preferences), from the environment; MAT3RA_HOST picks the host.
Optional: `pip install mat3ra-esse` turns on schema validation before anything is uploaded.
"""
import argparse, concurrent.futures, os, sys, threading, time, urllib.parse
from pathlib import Path

import requests
from mat3ra.api_client import APIClient

from run_document import load

try:  # optional: schema validation before anything is sent
    from mat3ra.esse import ESSE
    from mat3ra.esse.models.sample import SampleSchema
except ImportError:
    ESSE = SampleSchema = None

def holder(prop, measurement_id, sample_id, unit_id, repetition):
    """The property holder the platform stores: the data, where it came from (measurement, sample, workflow unit) and a
    repetition index — 0, since a measurement holds one sample and one loop property."""
    return {"data": prop,
            "source": {"type": "external",
                       "info": {"origin": {"_id": measurement_id, "cls": "Measurement"},
                                "subject": {"_id": sample_id, "cls": "Sample"},
                                "unitId": unit_id}},
            "exabyteId": [], "repetition": repetition}


def validate(parsed):
    """Validate every document against the ESSE schemas; returns the number of invalid ones. Skipped (returns 0) when the
    optional mat3ra-esse package is not installed."""
    if ESSE is None:
        return None  # not installed: the caller says so rather than reporting a pass
    esse = ESSE()
    schemas = {x["$id"]: x for x in esse.schemas}
    errors = 0
    for smp in parsed["samples"].values():
        try:
            SampleSchema(**smp); esse.validate(smp, schemas["sample"])
        except Exception as e:
            errors += 1; print("SAMPLE INVALID", smp["label"], str(e)[:200])
    for label, m in parsed["measurements"].items():
        m = {k: v for k, v in m.items() if k != "_records"}; m["_sample"] = {"_id": "dryrun", "cls": "Sample", "slug": label}
        try:
            esse.validate(m, schemas["measurement"])
        except Exception as e:
            errors += 1; print("MEASUREMENT INVALID", label, str(e)[:300]); break
    unvalidated = set()
    for label, uid, prop, rep in parsed["properties"]:
        # by the property's own name: NLR's thickness, atomic fractions and I-V curve are not the
        # hysteresis loop, and ESSE has no schema for them yet, so they are reported, not failed
        schema_id = f"properties-directory/non-scalar/{prop['name'].replace('_', '-')}"
        schema = schemas.get(schema_id) or schemas.get(schema_id.replace("non-scalar", "scalar"))
        if schema is None:
            unvalidated.add(prop["name"]); continue
        try:
            esse.validate(prop, schema)
            esse.validate(holder(prop, "dryrun", "dryrun", uid, rep), schemas["property/holder"])
        except Exception as e:
            errors += 1; print("PROPERTY INVALID", label, str(e)[:300])
    if unvalidated:
        print("no ESSE schema yet, not validated:", ", ".join(sorted(unvalidated)))
    return errors



def base_url(host):
    """`https://` unless told otherwise: a bare hostname becomes https, localhost/127.0.0.1 http, a URL is kept."""
    host = host.rstrip("/")
    if host.startswith(("http://", "https://")):
        return host
    return ("http://" if host.split(":")[0] in ("localhost", "127.0.0.1") else "https://") + host


def find(endpoint, query, owner_id, limit=100):
    """The account's entities matching `query` — a query bypasses the route's account scoping, so every lookup is
    narrowed. A page as long as the limit is refused: a missed member means a duplicate on the next run."""
    found = endpoint.list(dict(query, **{"owner._id": owner_id}), {"limit": limit})
    if len(found) >= limit and limit > 1:
        raise SystemExit(f"{endpoint.name}: more than {limit} match — this script cannot page yet; stop rather than duplicate")
    return found


def account_id(client, slug_or_name):
    """`--account <slug>` → the id of that account: the slug the platform shows it under, else its display name."""
    accounts = client.list_accounts()
    for field in ("slug", "name"):
        account = next((a for a in accounts if a.get(field) == slug_or_name), None)
        if account:
            return account["_id"]
    raise SystemExit(f"account '{slug_or_name}' is not one of yours: "
                     f"{', '.join(a.get('slug') or a['name'] for a in accounts)}")


THREAD = threading.local()


def thread_client(client):
    """A client of the calling thread's own: the endpoints keep the last response on the connection they share, so
    the file workers cannot use one between them. Building one costs nothing — no request is made until it is used."""
    if not hasattr(THREAD, "client"):
        THREAD.client = APIClient(host=client.host, port=client.port, version=client.version, secure=client.secure,
                                  auth=client.auth, timeout_seconds=client.timeout_seconds)
    return THREAD.client


def put_file(client, name, payload, owner_id):
    """One file into the account's file store: a file on disk through a signed PUT, text through the files route.
    Eight connections at once is enough to make a name resolution fail now and then, so a refused connection is
    tried again twice before it takes the run down with it."""
    for attempt in range(3):
        try:
            if isinstance(payload, Path):
                return client.files.put(payload, name, account_id=owner_id)
            return client.files.create(name, payload, account_id=owner_id)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def merge_metadata(existing, incoming):
    """`incoming` on top of `existing`, keeping what neither replaces. A list grows by the entries it
    does not already hold - a re-upload brings deposition records the set has never seen,
    and taking only absent keys would drop them because `deposition` is already there."""
    merged = dict(existing)
    for key, value in incoming.items():
        held = merged.get(key)
        if isinstance(held, list) and isinstance(value, list):
            merged[key] = held + [v for v in value if v not in held]
        elif isinstance(held, dict) and isinstance(value, dict):
            merged[key] = merge_metadata(held, value)
        else:
            merged[key] = value
    return merged


def ensure_set(endpoint, doc, owner_id):
    """The set with this name in the account, created when missing; returns (set, created).
    An existing set takes any metadata it does not have yet - a later upload may carry a
    deposition record the set was created without."""
    found = find(endpoint, {"isEntitySet": True, "name": doc["name"]}, owner_id, 5)
    if not found:
        return endpoint.create_set(dict(doc, owner={"_id": owner_id})), True

    existing = found[0]
    merged = merge_metadata(existing.get("metadata") or {}, doc.get("metadata") or {})
    if merged != (existing.get("metadata") or {}):
        endpoint.update_set(existing["_id"], {"metadata": merged})
        existing = dict(existing, metadata=merged)
    return existing, False


FILE_GROUPS = ("records", "loops")


def run_files(parsed, groups=("records",)):
    """Every file this run puts, as (name, payload) pairs. `groups` names what to include per
    measurement: "records" for the record JSONs, "loops" for the loop arrays and plots, which are
    large. The set's own files - NLR's grid, the photographs of the piece - are few and always go.
    `name` carries the label it belongs to so `destination` can address it."""
    unknown = set(groups) - set(FILE_GROUPS)
    if unknown:
        raise SystemExit(f"unknown file group(s): {', '.join(sorted(unknown))}; choose from {', '.join(FILE_GROUPS)}")
    files = [(f"set/{name}", payload) for name, payload in parsed["set_files"]]
    for label, file_list in parsed["files"].items():
        files += [(f"{label}/{name}", payload) for name, payload in file_list
                  if ("loops" if name.startswith("loops/") else "records") in groups]
    return files


def destination(name, set_id, measurement_ids):
    """Where one of `run_files`' entries is put: the set's own, or the measurement it belongs to."""
    label, _, rest = name.partition("/")
    if label == "set":
        return f"sets/{set_id}/{rest}"
    return f"measurements/{measurement_ids[label]}/{rest}"


def upload(client, parsed, files=("records",)):
    """The run onto its Sample Set: the set, its samples, the measurement set, one measurement per
    sample, the files and the properties. `files` names which groups to upload - see FILE_GROUPS;
    an empty list uploads none and keeps the raw records in each measurement's metadata instead.
    Idempotent: sets by run name, members by name/label; files re-put; properties posted only when
    missing."""
    uploads = run_files(parsed, files) if files else []
    run_name = parsed["run"]
    owner = {"_id": client.my_account.id}
    sample_set, created_set = ensure_set(client.samples, parsed["sample_set"], owner["_id"])
    set_id = sample_set["_id"]
    in_set = {s.get("label"): s for s in find(client.samples, {"inSet._id": set_id, "isEntitySet": {"$ne": True}}, owner["_id"], 500)}
    sample_ids, created = {}, 0
    for label, sample_doc in parsed["samples"].items():
        if label in in_set:
            sample_ids[label] = in_set[label]["_id"]
            continue
        doc = client.samples.create(dict(sample_doc, owner=owner))
        client.samples.move_to_set(doc["_id"], None, set_id)
        sample_ids[label] = doc["_id"]
        created += 1
    print(f"sample set {set_id} ({sample_set['name']}, ordered{', created' if created_set else ''}): {len(sample_ids)} samples, {created} created")
    measurement_set, created_measurement_set = ensure_set(client.measurements, parsed["measurement_set"], owner["_id"])
    existing = {m["name"]: m for m in find(client.measurements, {"inSet._id": measurement_set["_id"], "isEntitySet": {"$ne": True}}, owner["_id"], 500)}
    measurement_ids, measurements_created = {}, 0
    for label, measurement_doc in parsed["measurements"].items():
        if measurement_doc["name"] in existing:
            measurement_ids[label] = existing[measurement_doc["name"]]["_id"]
            continue
        body = dict(measurement_doc)
        body["_sample"] = {"_id": sample_ids[label], "cls": "Sample"}
        records = parsed.get("records_by_sample", {}).get(label)
        if not uploads and records:  # no file store: keep the raw records in the measurement's metadata
            body["metadata"] = dict(body["metadata"], records=records)
        doc = client.measurements.create(dict(body, owner=owner))
        client.measurements.move_to_set(doc["_id"], None, measurement_set["_id"])
        measurement_ids[label] = doc["_id"]
        measurements_created += 1
    print(f"measurement set {measurement_set['_id']} ({run_name}, ordered{', created' if created_measurement_set else ''}): "
          f"{len(measurement_ids)} measurements, {measurements_created} created")
    if uploads:
        # one request per file (~1-2 s each), eight in flight
        jobs = [(destination(name, set_id, measurement_ids), payload) for name, payload in uploads]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for done, _ in enumerate(pool.map(lambda job: put_file(thread_client(client), *job, owner["_id"]), jobs), 1):
                if done % 200 == 0:
                    print(f"  files: {done}/{len(jobs)}", flush=True)
        print(f"files: {len(jobs)} put")
    posted = 0
    for label, unit_id, prop, repetition in parsed["properties"]:  # properties/create is not idempotent: skip what is there
        present = find(client.properties, {"source.info.origin._id": measurement_ids[label], "data.name": prop["name"],
                                           "repetition": repetition}, owner["_id"], 1)
        if present:
            continue
        client.properties.create(dict(holder(prop, measurement_ids[label], sample_ids[label], unit_id, repetition), owner=owner))
        posted += 1
    print(f"properties: {posted} posted, {len(parsed['properties']) - posted} already present")


def main():
    """Command line: validate the run documents, then upload them."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("documents", nargs="+", metavar="RUN.JSON", help="run documents, as a parser writes them")
    ap.add_argument("--host", default=os.environ.get("MAT3RA_HOST", "localhost:3000"),
                    help="web app host or URL (or MAT3RA_HOST); https unless localhost, e.g. dev.mat3ra.com")
    ap.add_argument("--account", help="slug of the account the data belongs to (reads scoped to it, writes owned by it)")
    ap.add_argument("--files", nargs="*", default=["records"], metavar="GROUP",
                    help=f"which file groups to upload ({', '.join(FILE_GROUPS)}); pass --files with no value "
                         "to upload none and keep the raw records in each measurement's metadata")
    ap.add_argument("--dry-run", action="store_true", help="validate the documents and stop")
    a = ap.parse_args()

    runs = [load(path) for path in a.documents]
    counts = [validate(run) for run in runs]
    if any(count is None for count in counts):
        print("validation: SKIPPED — mat3ra-esse is not installed (see requirements.txt); nothing was checked")
        errors = 0
    else:
        errors = sum(counts)
        print("validation:", "OK" if errors == 0 else f"{errors} invalid documents")
    if errors or a.dry_run:
        sys.exit(1 if errors else 0)

    url = urllib.parse.urlsplit(base_url(a.host))
    address = {"host": url.hostname, "port": url.port or (443 if url.scheme == "https" else 80), "secure": url.scheme == "https"}
    client = APIClient.authenticate(**address)
    if a.account:
        client = APIClient.authenticate(account_id=account_id(client, a.account), **address)
    for run in runs:
        upload(client, run, files=a.files)


if __name__ == "__main__":
    main()
