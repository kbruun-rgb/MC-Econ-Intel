"""Builds the "new finding" email for a published narrative snippet.

Who gets it: every portal user except those who unsubscribed
(EmailOptOut) and test/excluded addresses (config.EMAIL_EXCLUDE_*).

How it is sent: not from this app. The portal builds one message per
recipient (so each carries its own signed unsubscribe link) and
send_narrative_email.py hands them to Kayla's Gmail connector, which sends
them after she approves. This module only renders and records.

The chart is embedded as an inline attachment (cid:att0): Gmail's connector
strips remote images, and a chart URL on this site would sit behind a login
anyway.
"""
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from markupsafe import Markup, escape

from app import db
from app.models import ActivityEvent, EmailOptOut, NarrativeEmailSend, User
from app.library_scan import find_theme
from app.narrative import related_dashboard_link, render_paragraphs, topic_label
from config import EMAIL_EXCLUDE_ADDRESSES, EMAIL_EXCLUDE_SUFFIXES, EMAIL_FOOTER_ADDRESS, SITE_BASE_URL

TEAL = "#018383"
INK = "#2B2B2B"
GRAY = "#757575"
LIGHT = "#E5E5E5"
MIN_DAYS_BETWEEN_SENDS = 14


def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="narrative-email-unsubscribe")


def unsubscribe_token(user):
    return _serializer().dumps(user.id)


def user_from_token(token):
    try:
        user_id = _serializer().loads(token)
    except BadSignature:
        return None
    return db.session.get(User, user_id)


def is_subscribed(user):
    return EmailOptOut.query.filter_by(user_id=user.id).first() is None


def set_subscribed(user, subscribed):
    existing = EmailOptOut.query.filter_by(user_id=user.id).first()
    if subscribed and existing:
        db.session.delete(existing)
    elif not subscribed and not existing:
        db.session.add(EmailOptOut(user_id=user.id))
    db.session.commit()


def excluded_reason(user):
    """Why a user would NOT get the email, or None if they would."""
    email = user.email.lower()
    if email.endswith(tuple(EMAIL_EXCLUDE_SUFFIXES)) or email in EMAIL_EXCLUDE_ADDRESSES:
        return "excluded address"
    if not is_subscribed(user):
        return "unsubscribed"
    return None


def recipients():
    return [u for u in User.query.order_by(User.email).all() if excluded_reason(u) is None]


def skipped():
    """(user, reason) for everyone left out -- shown on the preview so an
    unexpected omission is visible before sending."""
    return [(u, r) for u in User.query.order_by(User.email).all() if (r := excluded_reason(u))]


def previous_sends(snippet_id=None):
    q = NarrativeEmailSend.query
    if snippet_id is not None:
        q = q.filter_by(snippet_id=snippet_id)
    return q.order_by(NarrativeEmailSend.sent_at.desc()).all()


def send_guard(snippet):
    """Problems to confirm before sending, as plain-English strings."""
    problems = []
    if snippet.status != "approved":
        problems.append(f"Snippet is '{snippet.status}', not approved/live.")
    if previous_sends(snippet.id):
        problems.append("This finding was already emailed.")
    recent = previous_sends()
    if recent and recent[0].sent_at is not None:
        sent_at = recent[0].sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - sent_at
        if age < timedelta(days=MIN_DAYS_BETWEEN_SENDS):
            problems.append(f"Last email went out {age.days} day(s) ago (guideline: at least {MIN_DAYS_BETWEEN_SENDS}).")
    if not snippet.chart_image:
        problems.append("Snippet has no chart image.")
    if not (snippet.related_geography and snippet.related_theme_slug and find_theme(snippet.related_geography, snippet.related_theme_slug)):
        problems.append("No related dashboard set, so the button falls back to the site home page.")
    return problems


def engagement(send):
    """How many of the recipients who could have received a send were active
    on the site in the 7 days after it. Everyone active counts, not just
    people who clicked: there is deliberately no click tracking (corporate
    link scanners would inflate it). Users who joined after the send are
    left out.
    """
    if send.sent_at is None:
        return None
    window_end = send.sent_at + timedelta(days=7)
    active = {
        row[0]
        for row in db.session.query(ActivityEvent.user_id)
        .filter(ActivityEvent.created_at >= send.sent_at, ActivityEvent.created_at <= window_end)
        .distinct()
    }
    eligible = [u for u in recipients() if u.created_at is None or u.created_at <= send.sent_at]
    return len([u for u in eligible if u.id in active]), len(eligible)


def _abs(url):
    return SITE_BASE_URL.rstrip("/") + url if url.startswith("/") else url


def _style_links(markup):
    text = str(markup).replace('href="/', f'href="{SITE_BASE_URL.rstrip("/")}/')
    return Markup(text.replace("<a ", f'<a style="color:{TEAL};" '))


def build_email(snippet, user):
    """The subject plus HTML and plain-text bodies for one recipient. Must be
    called inside a request context (url_for) -- the script and the admin
    preview both provide one.
    """
    dash = related_dashboard_link(snippet)
    cta_url = _abs(dash[0]) if dash else SITE_BASE_URL
    cta_label = f"Explore the {dash[1]} data" if dash else "Explore the data"
    unsub_url = _abs(url_for("narrative.email_unsubscribe", token=unsubscribe_token(user)))
    topic = topic_label(snippet.topic_slug)
    paragraphs = [_style_links(p) for p in render_paragraphs(snippet.body)]
    plain_paragraphs = [p.strip() for p in snippet.body.split("\n\n") if p.strip()]
    address = f"<br>{escape(EMAIL_FOOTER_ADDRESS)}" if EMAIL_FOOTER_ADDRESS else ""

    chart_html = ""
    if snippet.chart_image:
        caption = (
            f'<p style="margin:6px 0 0;font-size:12px;line-height:1.4;color:{GRAY};">{escape(snippet.chart_caption)}</p>'
            if snippet.chart_caption
            else ""
        )
        chart_html = (
            f'<tr><td style="padding:0 32px 20px;">'
            f'<img src="cid:att0" alt="{escape(snippet.chart_caption or snippet.headline)}" width="536" '
            f'style="display:block;width:100%;max-width:536px;height:auto;border:1px solid {LIGHT};">{caption}</td></tr>'
        )

    body_html = "".join(
        f'<p style="margin:0 0 14px;font-size:16px;line-height:1.55;color:{INK};">{p}</p>' for p in paragraphs
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#F4F4F4;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F4F4;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#FFFFFF;font-family:'Proxima Nova','Avenir Next','Gill Sans','Trebuchet MS',Arial,sans-serif;">
<tr><td style="background:{TEAL};padding:14px 32px;color:#FFFFFF;font-size:13px;letter-spacing:0.04em;text-transform:uppercase;">Morning Consult Economic Intelligence</td></tr>
<tr><td style="padding:28px 32px 6px;">
<p style="margin:0 0 6px;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:{TEAL};">{escape(topic)}</p>
<h1 style="margin:0 0 18px;font-size:24px;line-height:1.25;color:{INK};">{escape(snippet.headline)}</h1>
</td></tr>
{chart_html}
<tr><td style="padding:0 32px 8px;">{body_html}</td></tr>
<tr><td style="padding:8px 32px 32px;">
<a href="{escape(cta_url)}" style="display:inline-block;background:{TEAL};color:#FFFFFF;text-decoration:none;font-size:15px;font-weight:bold;padding:12px 22px;border-radius:6px;">{escape(cta_label)}</a>
<p style="margin:10px 0 0;font-size:12px;color:{GRAY};">You will be asked to sign in with your portal login.</p>
</td></tr>
<tr><td style="border-top:1px solid {LIGHT};padding:18px 32px 24px;font-size:12px;line-height:1.5;color:{GRAY};">
You are receiving this because you have a login to the Morning Consult Economic Intelligence portal. We send these occasionally, when there is a finding worth a look.
<a href="{escape(unsub_url)}" style="color:{GRAY};">Unsubscribe</a>, or reply to this email and we will take you off the list.{address}
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    text_parts = [snippet.headline, ""]
    text_parts += [p + "\n" for p in plain_paragraphs]
    text_parts += [f"{cta_label}: {cta_url}", "(You will be asked to sign in with your portal login.)", ""]
    text_parts += [
        "You are receiving this because you have a login to the Morning Consult Economic Intelligence portal.",
        f"Unsubscribe: {unsub_url} (or reply to this email and we will take you off the list.)",
    ]
    if EMAIL_FOOTER_ADDRESS:
        text_parts.append(EMAIL_FOOTER_ADDRESS)

    return {
        "to": user.email,
        "subject": snippet.headline,
        "html": html,
        "text": "\n".join(text_parts),
    }
