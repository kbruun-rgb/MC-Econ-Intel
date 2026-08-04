import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
