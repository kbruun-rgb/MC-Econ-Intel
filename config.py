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

# Content source roots. These directories are read live -- nothing from them
# is ever copied into this project.
ECON_LIBRARY_ROOT = r"G:\Shared drives\mc_econ\Econ Team\Econ Data Library"
ANALYSES_ROOT = r"C:\Users\kayla\Desktop\Kayla\Claude Helper Tools\Analyses"

# Theme vocabulary shared by the dashboards library and the reports theme
# filter, used to best-guess a theme tag for each analysis from its slug.
THEME_KEYWORDS = {
    "CHI": ["chi"],
    "Consumer Spending": ["spending", "consumer-spending", "mdw", "memorial-day"],
    "Jobs & Labor": ["jobs", "labor", "unemployment", "nfp", "payroll"],
    "Housing": ["housing", "mortgage"],
    "Inflation & Supply Chains": ["inflation", "cpi", "supply-chain", "price"],
    "Price Response Indicators": ["pri", "price-response"],
    "Household Finances": ["household", "finance", "income"],
    "Weekly Pulse": ["weekly", "pulse"],
    "Geopolitical Risk": ["geopolitical", "gpr", "political"],
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
