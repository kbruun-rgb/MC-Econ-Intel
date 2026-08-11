import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Neon (and most Postgres hosts) hand out a `postgres://` or `postgresql://`
# URL, but the app uses the psycopg3 driver (better wheel support on newer
# Python than psycopg2), which needs the `postgresql+psycopg://` dialect
# prefix -- translate rather than asking for a hand-edited URL.
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    if _database_url.startswith("postgres://"):
        _database_url = _database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif _database_url.startswith("postgresql://"):
        _database_url = _database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Content source roots. Locally these are read live -- nothing from them is
# copied. When CONTENT_SOURCE=cloud (set on Render), create_app() overwrites
# these two module attributes with a local cache hydrated from Cloudflare R2
# *before* any blueprint imports them -- see app/cloud_storage.py. Everything
# downstream (library_scan.py, files.py) just reads a local folder either way.
ECON_LIBRARY_ROOT = r"G:\Shared drives\mc_econ\Econ Team\Econ Data Library"
ANALYSES_ROOT = r"C:\Users\kayla\Desktop\Kayla\Claude Helper Tools\Analyses"
BIBLE_ROOT = r"C:\Users\kayla\Desktop\Kayla\Econ Bible"
INDUSTRY_REPORTS_ROOT = (
    r"G:\Shared drives\mc_econ\Econ Team\U.S. Consumer Spending Data\Data Process\industry report\reports"
)

# Top-level ("## ") sections to strip entirely from a specific Bible file
# before it goes into /llms.txt or the "Connect with AI" download -- for
# content that's legitimately useful to keep in the Bible for internal
# Claude sessions (e.g. how to pull live data from MC's internal API) but
# has no business going into anything public or handed to a client. Found
# by manual review, not auto-detection -- deliberately a human judgment
# call per file, not a pattern-matching filter that could miss variants or
# over-redact something harmless.
BIBLE_REDACTED_SECTIONS = {
    ("data-series", "consumer-health-index-chi.md"): ["Data Access"],
}

# Only these Econ Bible categories feed the public /llms.txt guidance file
# (see app/bible_scan.py) -- durable, vetted methodology and interpretive
# knowledge. Deliberately excludes journal/ and current-state/, which are
# Kayla's raw, unvetted, dated working theories -- not something a client's
# AI agent should repeat back as settled Morning Consult analysis. For
# current-state inferences, the guidance file points agents at the site's
# own dated Analysis & Reports section instead.
BIBLE_LLMS_CATEGORIES = ["frameworks", "patterns", "playbooks", "data-series", "style-guide"]

CONTENT_SOURCE = os.environ.get("CONTENT_SOURCE", "local")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://mc-econ-intel.onrender.com")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")

# Theme vocabulary shared by the dashboards library and the reports theme
# filter, used to best-guess a theme tag for each analysis from its slug.
# The dict key is also what's displayed as the theme name, so it's spelled
# out in full rather than using the "CHI" acronym.
THEME_KEYWORDS = {
    "Consumer Health Index": ["chi"],
    "Consumer Spending": ["spending", "consumer-spending", "mdw", "memorial-day"],
    "Jobs & Labor": ["jobs", "labor", "unemployment", "nfp", "payroll"],
    "Housing": ["housing", "mortgage"],
    "Inflation & Supply Chains": ["inflation", "cpi", "supply-chain", "price"],
    "Price Response Indicators": ["pri", "price-response"],
    "Household Finances": ["household", "finance", "income"],
    "Weekly Pulse": ["weekly", "pulse"],
    "Geopolitical Risk": ["geopolitical", "gpr", "political"],
}

# Dashboard theme folder names are derived directly from the Econ Data
# Library's folder names (e.g. "US CHI" -> theme "CHI"), which sometimes
# don't match the display name we want. Keyed by (geography, raw theme) so
# the same raw name can be overridden differently per geography (e.g. "Jobs
# & Labor" reads as "Global Labor" only under Global, not under US).
DASHBOARD_THEME_DISPLAY_NAMES = {
    ("US", "CHI"): "Consumer Health Index",
    ("Global", "Jobs & Labor"): "Global Labor",
    ("Global", "Price Response Indicators"): "International Price Response Indicators",
}

# Individual dashboard file titles default to a humanized filename (e.g.
# "labor_dashboard_mc.html" -> "Labor Dashboard Mc"), which doesn't always
# read well or distinguish similarly-named files -- override by filename
# here when that happens.
DASHBOARD_FILE_TITLES = {
    "labor_dashboard_mc.html": "Weekly Labor Dashboard",
}

# Dashboards with no built-in toggleTheme() get a generic CSS invert-filter
# fallback so they're never stuck dark (see dashboard_detail.html), but that
# distorts hue on any accent colors and never looks quite right. Where a
# dashboard's dark colors are known (mostly CSS variables + a handful of
# hardcoded hex values, not canvas-baked), a real light-theme override here
# looks correct instead of merely inverted -- keyed by filename, injected
# in place of the generic fallback. Canvas-drawn chart colors (Chart.js grid/
# tick/tooltip options, data-series line colors) can't be reached by CSS at
# all, so those stay as originally authored; they're mostly neutral grays
# that read fine on a light background regardless.
DASHBOARD_LIGHT_MODE_OVERRIDES = {
    "consumer_financial_health_dashboard.html": """
        :root {
          --bg: #f8fafc;
          --surface: #ffffff;
          --border: rgba(15,23,42,0.08);
          --text: #0f172a;
          --text-dim: #64748b;
          --text-mid: #475569;
        }
        .header h1 { color:#0f172a; }
        .kpi-card { background:#ffffff; border-color:rgba(15,23,42,0.08); box-shadow:0 1px 2px rgba(15,23,42,0.04); }
        .kpi-value { color:#0f172a; }
        .tab-btn:hover:not(.active) { color:#334155; }
        .filters label { color:#475569; }
        .demo-select { border-color:rgba(15,23,42,0.15); color:#1e293b; }
        .demo-select:hover { border-color:rgba(15,23,42,0.35); }
        .demo-select option { color:#1e293b; }
        .chart-container { background:#ffffff; border-color:rgba(15,23,42,0.06); box-shadow:0 1px 2px rgba(15,23,42,0.04); }
        .chart-title { color:#0f172a; }
        .dl-btn { border-color:rgba(15,23,42,0.15); color:#475569; }
        .dl-btn:hover { border-color:rgba(15,23,42,0.35); color:#1e293b; }
        .legend-tag { border-color:rgba(15,23,42,0.12); color:#1e293b; }
        .section-label { color:#475569; }
        .loading-overlay { background:rgba(248,250,252,0.92); }
        .spinner { border-color:rgba(15,23,42,0.12); }
        .legend-tag.agg:hover, .legend-tag.toggleable:hover { border-color:rgba(15,23,42,0.4); }
        .toggle-track { background:rgba(15,23,42,0.15); }
        #date-range-label { color:#475569 !important; }
    """,
}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me-before-any-real-deployment")
    # Falls back to a local SQLite file when DATABASE_URL isn't set, so the
    # app still runs with zero setup -- but that file doesn't survive a
    # Render restart, so DATABASE_URL (a Neon connection string) is required
    # for anything actually deployed.
    SQLALCHEMY_DATABASE_URI = _database_url or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Neon suspends its compute (and drops connections) after a few minutes
    # idle. Without pool_pre_ping, SQLAlchemy hands out a pooled connection
    # without checking it's still alive, which throws AdminShutdown on the
    # first request after any idle gap. pre_ping tests it with a cheap query
    # first and transparently reconnects if it's dead.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
