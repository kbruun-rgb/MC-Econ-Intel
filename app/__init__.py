from flask import Flask, redirect, url_for, request
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")

    # Must happen before any blueprint is imported: those blueprints (via
    # app.library_scan / app.files) do `from config import ECON_LIBRARY_ROOT,
    # ANALYSES_ROOT` at import time, so config's module attributes have to
    # already point at the hydrated cache by then.
    import config

    if config.CONTENT_SOURCE == "cloud":
        from app.cloud_storage import hydrate_from_cloud

        config.ECON_LIBRARY_ROOT, config.ANALYSES_ROOT = hydrate_from_cloud()

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.auth import auth_bp
    from app.main import main_bp
    from app.dashboards import dashboards_bp
    from app.reports import reports_bp
    from app.files import files_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(files_bp)

    # Route-level @login_required decorators guard every page and file
    # response individually (see each blueprint) -- this hook is a second,
    # coarse-grained backstop so a newly added route can never accidentally
    # ship unauthenticated by omission.
    EXEMPT_ENDPOINTS = {"auth.login", "static"}

    @app.before_request
    def enforce_login():
        if request.endpoint in EXEMPT_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        return None

    with app.app_context():
        db.create_all()

    return app
