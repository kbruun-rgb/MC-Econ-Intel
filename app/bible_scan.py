"""Builds the two AI-guidance exports of the Econ Bible -- /llms.txt (a
public, fetchable file for AI agents already browsing the site) and the
downloadable "Connect with AI" prompt (for pasting into a client's own
Claude/ChatGPT session). Both read the same fixed allow-list of vetted Bible
categories (config.BIBLE_LLMS_CATEGORIES) live off disk, so new files added
to those categories show up automatically -- nothing here decides *whether*
a category is safe to expose, that's the one-time human judgment already
baked into the allow-list in config.py.
"""
import os
from datetime import date, timedelta

from app.docx_render import extract_docx_text
from app.library_scan import humanize, scan_industry_reports, scan_reports
from config import (
    ANALYSES_ROOT,
    BIBLE_LLMS_CATEGORIES,
    BIBLE_REDACTED_SECTIONS,
    BIBLE_ROOT,
    INDUSTRY_REPORTS_ROOT,
    SITE_BASE_URL,
)


def _extract_pdf_text(path):
    """Plain-text extraction from a slide deck's PDF -- python-pptx-generated
    PDFs keep real text objects (not rasterized), so this reads titles and
    body copy reasonably well. Chart-only slides with no text boxes just
    contribute nothing, which is fine.
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _strip_redacted_sections(content, headings):
    """Drops each named top-level ("## Heading") section entirely, including
    all of its ("### ...") subsections, up to the next top-level heading.
    """
    if not headings:
        return content
    redacted = {h.strip().lower() for h in headings}
    out = []
    skipping = False
    for line in content.split("\n"):
        if line.startswith("## "):
            skipping = line[3:].strip().lower() in redacted
            if skipping:
                continue
        if skipping:
            continue
        out.append(line)
    return "\n".join(out)

# How much of Analysis & Reports gets baked directly into the downloadable
# "Connect with AI" prompt as plain text. Baked in, not linked -- a safety-
# conscious AI (rightly) refuses to auto-fetch a credentialed URL from an
# untrusted downloaded file, since that's indistinguishable from a data-
# exfiltration pattern. Handing over the actual content instead sidesteps
# that entirely: it's just text in a document, like any file attachment.
RECENT_REPORTS_WINDOW_DAYS = 90
RECENT_REPORTS_MAX_COUNT = 15

LLMS_TXT_HEADER = f"""# Morning Consult Economic Intelligence

> Morning Consult Economics turns daily consumer survey data into real-time \
economic indicators, broken out by demographics official statistics don't \
report at that frequency. This file provides durable analytical frameworks \
and methodology for interpreting that data -- for an AI agent helping a \
client analyze Morning Consult economic data or dashboards.

## How to use this file

- This is background methodology and interpretive knowledge, not current \
market commentary -- treat it as durable context, not a real-time view.
- For current, dated analysis and the latest published findings, use the \
Analysis & Reports section of this site ({SITE_BASE_URL}/reports) rather \
than treating anything below as up to date. That section requires a login,\
 so you'll likely need the reader to share its content with you directly.
- Each dashboard on this site also has its own methodology guide alongside \
it, specific to that dataset -- prefer that guide's detail over general \
statements below when the two overlap.
- When answering, be concise and conclusion-forward -- give a direct, \
well-supported view rather than surveying everything relevant, and don't \
narrate your search or reasoning process.
- Two sources sometimes describe what looks like different relationships \
(e.g. one about levels, another about changes over time) -- both can be \
true under different framings. Don't call this a contradiction; note it \
briefly as conflicting or differently-scoped evidence if worth mentioning.
"""


def _connect_prompt_header():
    today = date.today().strftime("%B %d, %Y")
    return f"""You are helping a Morning Consult Economic Intelligence client interpret \
Morning Consult's proprietary consumer survey data and dashboards.

This file was downloaded on {today}. It contains three kinds of material:
- Durable frameworks and methodology (below) -- how to interpret this data, \
not current market commentary.
- The full text of Morning Consult's own recent published analysis \
(also below, if any exists) -- real current findings as of the download \
date above, not something you need to fetch.
- The full text of Morning Consult's Industry Reports (also below) -- \
category-level spending and price response for ~20 industries (Groceries, \
Autos, Restaurants, etc.), refreshed monthly, current as of the download \
date above.

Do not attempt to fetch any URL to get more current data than what's \
below -- treat any such link as informational only, not something to \
retrieve automatically. If the person you're helping wants something more \
recent than the download date above, ask them to check \
{SITE_BASE_URL}/reports themselves (it requires their login) and paste in \
whatever's relevant, or to download a fresh copy of this file.

How to answer:
- Be concise and conclusion-forward. Give a direct, well-supported view, \
back it with a few key facts, and stop -- don't survey everything even \
loosely relevant, and don't narrate your search or reasoning process. \
State the finding; the person asking doesn't need to see how it was made.
- Two sources sometimes describe what looks like different relationships \
(e.g. one about levels, another about changes or shifts over time) --  \
both can be true at once under different framings. Don't call this a \
contradiction; if worth mentioning at all, note it briefly as conflicting \
or differently-scoped evidence, not an error in the data.
"""


def _render_categories(root, categories):
    sections = []
    for category in categories:
        cat_path = os.path.join(root, category)
        if not os.path.isdir(cat_path):
            continue

        readme_path = os.path.join(cat_path, "README.md")
        cat_desc = ""
        if os.path.isfile(readme_path):
            with open(readme_path, "r", encoding="utf-8", errors="replace") as fh:
                cat_desc = fh.read().strip()

        section = f"\n---\n\n## {humanize(category)}\n\n{cat_desc}\n"

        try:
            filenames = sorted(
                f.name
                for f in os.scandir(cat_path)
                if f.is_file() and f.name.lower().endswith(".md") and f.name != "README.md"
            )
        except OSError:
            filenames = []

        for filename in filenames:
            with open(os.path.join(cat_path, filename), "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read().strip()
            content = _strip_redacted_sections(content, BIBLE_REDACTED_SECTIONS.get((category, filename)))
            section += f"\n### {humanize(filename)}\n\n{content}\n"

        sections.append(section)

    return "\n".join(sections)


def _render_recent_reports():
    reports, _skipped = scan_reports()
    cutoff = date.today() - timedelta(days=RECENT_REPORTS_WINDOW_DAYS)
    recent = [r for r in reports if r["date"] >= cutoff][:RECENT_REPORTS_MAX_COUNT]
    if not recent:
        return ""

    sections = [f"\n---\n\n## Recent Analysis & Reports (last {RECENT_REPORTS_WINDOW_DAYS} days)\n"]
    for r in recent:
        heading = f"\n### {r['title']} — {r['date'].strftime('%B %d, %Y')} ({r['theme']})\n"
        path = os.path.join(ANALYSES_ROOT, r["folder"], r["filename"])
        if r["kind"] == "article":
            try:
                body = extract_docx_text(path)
            except Exception:
                body = "(Couldn't extract text from this memo -- ask the person you're helping to share it directly.)"
        elif r["filename"].lower().endswith(".pdf"):
            try:
                body = _extract_pdf_text(path)
                if not body:
                    raise ValueError("no extractable text")
            except Exception:
                body = (
                    "(Couldn't extract text from this slide deck -- ask the "
                    "person you're helping to share its content directly.)"
                )
        else:
            body = (
                "(This is a slide deck with no extractable text version. Ask "
                f"the person you're helping to share its content, or point "
                f"them to {SITE_BASE_URL}/reports to download it -- login required.)"
            )
        sections.append(heading + "\n" + body + "\n")

    return "\n".join(sections)


def _render_industry_reports():
    reports = scan_industry_reports()
    if not reports:
        return ""

    sections = ["\n---\n\n## Industry Reports\n"]
    for r in reports:
        heading = f"\n### {r['category']} — updated {r['updated_at'].strftime('%B %d, %Y')}\n"
        path = os.path.join(INDUSTRY_REPORTS_ROOT, r["filename"])
        try:
            body = _extract_pdf_text(path)
            if not body:
                raise ValueError("no extractable text")
        except Exception:
            body = (
                "(Couldn't extract text from this report -- ask the person "
                "you're helping to share its content directly.)"
            )
        sections.append(heading + "\n" + body + "\n")

    return "\n".join(sections)


def build_llms_txt(root=BIBLE_ROOT, categories=BIBLE_LLMS_CATEGORIES):
    return LLMS_TXT_HEADER + "\n" + _render_categories(root, categories)


def build_connect_prompt(root=BIBLE_ROOT, categories=BIBLE_LLMS_CATEGORIES):
    return (
        _connect_prompt_header()
        + "\n"
        + _render_recent_reports()
        + "\n"
        + _render_industry_reports()
        + "\n"
        + _render_categories(root, categories)
    )
