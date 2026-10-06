#!/usr/bin/env python3
"""AFM topography metrics already stored on the platform -> the properties they are.

UTK's uploader kept each site's image metrics in the measurement's metadata (`frames[].imageMetrics`)
under names of its own. This reads them back and posts the ESSE properties they correspond to, so the
Results tab shows them and they are comparable with any other instrument's. Only the unambiguous
metrics are mapped; peak-to-valley, kurtosis and correlation length wait for UTK to say how they were
computed. Idempotent: a property already present on a measurement is not posted again.

    derive_topography.py <measurement set id> [--dry-run]
"""
import argparse, os, sys, urllib.parse

from mat3ra.api_client import APIClient

from upload_run import account_id, base_url, find, holder

# imageMetrics key -> the ESSE property it is. Metres in, metres out.
METRICS = {
    "rq_m": {"name": "areal_surface_texture", "parameter": "Sq", "units": "m"},
    "ra_m": {"name": "areal_surface_texture", "parameter": "Sa", "units": "m"},
    "grain_radius_median_m": {"name": "grain_size", "statistic": "median", "units": "m"},
    "grain_radius_mean_m": {"name": "grain_size", "statistic": "mean", "units": "m"},
    "grain_radius_std_m": {"name": "grain_size", "statistic": "std", "units": "m"},
    "grain_radius_iqr_m": {"name": "grain_size", "statistic": "iqr", "units": "m"},
    "grain_coverage": {"name": "grain_coverage"},
}


def properties_of(measurement):
    """The properties one topography measurement's stored metrics stand for."""
    unit_id = measurement["workflow"]["subworkflows"][0]["units"][0]["flowchartId"]
    out = []
    for frame in (measurement.get("metadata") or {}).get("frames", []):
        for key, shape in METRICS.items():
            if key in frame.get("imageMetrics", {}):
                out.append((unit_id, dict(shape, value=frame["imageMetrics"][key])))
    return out


def derive(client, set_id, dry_run):
    owner_id = client.my_account.id
    measurements, skip = [], 0
    while True:  # the list route pages at 20 whatever the limit
        page = client.measurements.list({"inSet._id": set_id, "isEntitySet": {"$ne": True}, "owner._id": owner_id},
                                        {"limit": 20, "skip": skip})
        measurements += page
        skip += 20
        if len(page) < 20:
            break
    posted = present = 0
    for m in measurements:
        for unit_id, prop in properties_of(m):
            selector = {"source.info.origin._id": m["_id"], "data.name": prop["name"]}
            for key in ("parameter", "statistic"):
                if key in prop:
                    selector[f"data.{key}"] = prop[key]
            if find(client.properties, selector, owner_id, 1):
                present += 1
                continue
            if not dry_run:
                client.properties.create(dict(holder(prop, m["_id"], m["_sample"]["_id"], unit_id, 0), owner={"_id": owner_id}))
            posted += 1
    print(f"{len(measurements)} measurements: {posted} properties {'to post' if dry_run else 'posted'}, {present} already present")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set_id", help="the topography Measurement Set")
    ap.add_argument("--host", default=os.environ.get("MAT3RA_HOST", "localhost:3000"))
    ap.add_argument("--account", help="slug of the account the data belongs to")
    ap.add_argument("--dry-run", action="store_true", help="count what would be posted and stop")
    a = ap.parse_args()
    url = urllib.parse.urlsplit(base_url(a.host))
    address = {"host": url.hostname, "port": url.port or (443 if url.scheme == "https" else 80), "secure": url.scheme == "https"}
    client = APIClient.authenticate(**address)
    if a.account:
        client = APIClient.authenticate(account_id=account_id(client, a.account), **address)
    derive(client, a.set_id, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
