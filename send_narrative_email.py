"""Prepare (and record) a "new finding" email to portal subscribers.

This script never sends anything. It renders one message per recipient into
a manifest that Claude hands to Kayla's Gmail connector, which sends only
after she approves. Typical flow:

    python send_narrative_email.py preview 71          # who, what, any warnings
    python send_narrative_email.py prepare 71          # writes the manifest + chart
    python send_narrative_email.py prepare 71 --only kbruun@morningconsult.com   # test copy
    python send_narrative_email.py log 71 <count>      # after the real send

`log` is what stops a double-send and feeds the "sent so far" table on
/admin/narrative/<id>/email, so it is run after every real send (not after
a --only test).
"""
import argparse
import hashlib
import json
import os
import sys

from flask import current_app

from app import create_app, db
from app.models import NarrativeEmailSend
from app.narrative import get_snippet
from app.narrative_email import build_email, recipients, send_guard, skipped
from config import SITE_BASE_URL

SENDER = "kbruun@morningconsult.com"


def _snippet_or_exit(snippet_id):
    snippet = get_snippet(snippet_id)
    if snippet is None:
        sys.exit(f"No narrative snippet with id {snippet_id}.")
    return snippet


def cmd_preview(snippet_id):
    snippet = _snippet_or_exit(snippet_id)
    print(f"Snippet {snippet.id} [{snippet.status}] {snippet.topic_slug}: {snippet.headline}")
    problems = send_guard(snippet)
    print("Check before sending:" if problems else "No warnings.")
    for p in problems:
        print(f"  - {p}")
    to = recipients()
    print(f"\nRecipients ({len(to)}):")
    for u in to:
        print(f"  {u.email}")
    left_out = skipped()
    if left_out:
        print("\nLeft out:")
        for u, reason in left_out:
            print(f"  {u.email} ({reason})")


def cmd_prepare(snippet_id, out_dir, only, force, exclude=None):
    snippet = _snippet_or_exit(snippet_id)
    problems = send_guard(snippet)
    if problems and not force:
        print("Not preparing -- resolve or pass --force:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(2)
    to = recipients()
    if only:
        wanted = {e.strip().lower() for e in only}
        to = [u for u in to if u.email.lower() in wanted]
        missing = wanted - {u.email.lower() for u in to}
        if missing:
            sys.exit(f"Not in the recipient list (unknown, unsubscribed or excluded): {', '.join(sorted(missing))}")
    if exclude:
        drop = {e.strip().lower() for e in exclude}
        to = [u for u in to if u.email.lower() not in drop]
    if not to:
        sys.exit("No recipients.")

    out_dir = os.path.abspath(out_dir or os.path.join("content_cache", "narrative_emails", f"snippet-{snippet.id}"))
    os.makedirs(out_dir, exist_ok=True)
    chart_path = os.path.join(out_dir, "chart.png")
    with open(chart_path, "wb") as fh:
        fh.write(snippet.chart_image)
    digest = hashlib.sha256(snippet.chart_image).hexdigest()

    messages = []
    with current_app.test_request_context(base_url=SITE_BASE_URL):
        for user in to:
            built = build_email(snippet, user)
            messages.append(built)
    manifest = {
        "snippet_id": snippet.id,
        "test_only": bool(only),
        "chart_file_reference": f"sha256:{digest}:{chart_path.replace(os.sep, '/')}",
        "messages": messages,
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Prepared {len(messages)} message(s): {manifest_path}")


def cmd_log(snippet_id, count):
    snippet = _snippet_or_exit(snippet_id)
    db.session.add(
        NarrativeEmailSend(snippet_id=snippet.id, sent_by=SENDER, recipient_count=count, subject=snippet.headline[:255])
    )
    db.session.commit()
    print(f"Logged send of snippet {snippet.id} to {count} recipient(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview")
    p.add_argument("snippet_id", type=int)
    p = sub.add_parser("prepare")
    p.add_argument("snippet_id", type=int)
    p.add_argument("--out")
    p.add_argument("--only", nargs="+", help="Test copy: only these addresses.")
    p.add_argument("--exclude", nargs="+", help="Leave these addresses out of this one send only (they stay subscribed).")
    p.add_argument("--force", action="store_true", help="Prepare even if warnings were raised.")
    p = sub.add_parser("log")
    p.add_argument("snippet_id", type=int)
    p.add_argument("count", type=int)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.command == "preview":
            cmd_preview(args.snippet_id)
        elif args.command == "prepare":
            cmd_prepare(args.snippet_id, args.out, args.only, args.force, args.exclude)
        else:
            cmd_log(args.snippet_id, args.count)


if __name__ == "__main__":
    main()
