"""Cloud-content hydration: when CONTENT_SOURCE=cloud, the hosted app has no
access to the G: drive or the local Analyses folder, so on startup it
downloads whatever's in the R2 bucket into a local cache directory and reads
that instead. Content gets INTO the bucket via sync_to_cloud.py, run from a
machine that has real access to the source folders -- this module only
handles the read side.
"""
import os

CACHE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "content_cache")


def _r2_client():
    import boto3
    import config

    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT_URL,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
    )


def hydrate_from_cloud():
    """Downloads the bucket's dashboards/ and reports/ prefixes into a local
    cache directory. Returns (dashboards_root, reports_root).
    """
    import config

    client = _r2_client()
    cache_root = os.path.abspath(CACHE_ROOT)
    roots = {}

    for prefix in ("dashboards", "reports"):
        local_root = os.path.join(cache_root, prefix)
        os.makedirs(local_root, exist_ok=True)
        roots[prefix] = local_root

        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                relative = key[len(prefix) + 1 :]  # strip "dashboards/" or "reports/"
                if not relative:
                    continue
                local_path = os.path.join(local_root, *relative.split("/"))
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                client.download_file(config.R2_BUCKET_NAME, key, local_path)

    return roots["dashboards"], roots["reports"]
