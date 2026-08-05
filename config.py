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

CONTENT_SOURCE = os.environ.get("CONTENT_SOURCE", "local")
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
