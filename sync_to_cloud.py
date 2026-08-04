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
from app.library_scan import GUIDE_FILENAME, PUBLISH_FILENAME, scan_econ_library, scan_reports


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
            uploaded += 1

    print(f"Uploaded {uploaded} file(s) to r2://{config.R2_BUCKET_NAME}")


if __name__ == "__main__":
    main()
