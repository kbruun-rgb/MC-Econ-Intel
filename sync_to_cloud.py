"""Uploads the exact set of files the hosted app would serve -- dashboard
HTML + methodology guides, and published reports' deliverable + publish.json
-- to the Cloudflare R2 bucket. Run this locally (on a machine with real
access to the G: drive and the Analyses folder) whenever the library
changes or you publish/unpublish an analysis; the hosted app on Render picks
up the new content the next time it starts.

Usage:
    python sync_to_cloud.py
"""
import os

import boto3

import config
from app.library_scan import (
    GUIDE_FILENAME,
    PUBLISH_FILENAME,
    scan_econ_library,
    scan_industry_reports,
    scan_reports,
)


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT_URL,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
    )


def _upload(client, local_path, key):
    # R2 sets its own LastModified to upload time -- stash the file's real
    # mtime as custom metadata so the hosted app can show meaningful
    # "Updated" dates instead of always "today" (see app/cloud_storage.py).
    mtime = os.path.getmtime(local_path)
    client.upload_file(
        local_path, config.R2_BUCKET_NAME, key,
        ExtraArgs={"Metadata": {"sourcemtime": str(mtime)}},
    )


def _existing_keys(client, prefix):
    keys = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=f"{prefix}/"):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def main():
    missing = [
        name
        for name in ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
        if not getattr(config, name)
    ]
    if missing:
        raise SystemExit(f"Missing R2 config in .env: {', '.join(missing)}")

    client = _r2_client()
    uploaded = 0
    expected_keys = set()

    library = scan_econ_library()
    for themes in library.values():
        for entry in themes:
            folder = entry["folder"]
            local_folder = os.path.join(config.ECON_LIBRARY_ROOT, folder)
            filenames = [d["filename"] for d in entry["dashboards"]]
            if entry["guide_html"]:
                filenames.append(GUIDE_FILENAME)
            for filename in filenames:
                local_path = os.path.join(local_folder, filename)
                key = f"dashboards/{folder}/{filename}"
                _upload(client, local_path, key)
                expected_keys.add(key)
                uploaded += 1

    reports, _skipped = scan_reports()
    for r in reports:
        folder_path = os.path.join(config.ANALYSES_ROOT, r["folder"])
        for filename in (r["filename"], PUBLISH_FILENAME):
            local_path = os.path.join(folder_path, filename)
            if not os.path.isfile(local_path):
                continue
            key = f"reports/{r['folder']}/{filename}"
            _upload(client, local_path, key)
            expected_keys.add(key)
            uploaded += 1

    # Only the allow-listed, vetted Bible categories (see
    # config.BIBLE_LLMS_CATEGORIES) -- feeds /llms.txt. journal/ and
    # current-state/ are deliberately never synced here.
    for category in config.BIBLE_LLMS_CATEGORIES:
        cat_path = os.path.join(config.BIBLE_ROOT, category)
        if not os.path.isdir(cat_path):
            continue
        for f in os.scandir(cat_path):
            if not f.is_file() or not f.name.lower().endswith(".md"):
                continue
            key = f"bible/{category}/{f.name}"
            _upload(client, f.path, key)
            expected_keys.add(key)
            uploaded += 1

    for r in scan_industry_reports():
        local_path = os.path.join(config.INDUSTRY_REPORTS_ROOT, r["filename"])
        key = f"industry_reports/{r['filename']}"
        _upload(client, local_path, key)
        expected_keys.add(key)
        uploaded += 1

    # Mirror sync: anything in the bucket that's no longer expected (an
    # unpublished report, a removed/renamed dashboard file, a retired
    # industry category) has to be actively deleted, or the hosted app --
    # which only ever reads what's in the bucket -- keeps serving it
    # forever even after it's gone locally.
    stale_keys = (
        _existing_keys(client, "dashboards")
        | _existing_keys(client, "reports")
        | _existing_keys(client, "bible")
        | _existing_keys(client, "industry_reports")
    ) - expected_keys
    if stale_keys:
        client.delete_objects(
            Bucket=config.R2_BUCKET_NAME,
            Delete={"Objects": [{"Key": k} for k in stale_keys]},
        )

    print(f"Uploaded {uploaded} file(s), removed {len(stale_keys)} stale file(s) from r2://{config.R2_BUCKET_NAME}")


if __name__ == "__main__":
    main()
