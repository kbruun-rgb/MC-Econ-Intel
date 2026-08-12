from flask import Flask, redirect, url_for, request
from flask_login import LoginManager, current_user, login_user
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

        (
            config.ECON_LIBRARY_ROOT,
            config.ANALYSES_ROOT,
            config.BIBLE_ROOT,
            config.INDUSTRY_REPORTS_ROOT,
        ) = hydrate_from_cloud()

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
    from app.industry_reports import industry_reports_bp
    from app.topics_routes import topics_bp
    from app.files import files_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(industry_reports_bp)
    app.register_blueprint(topics_bp)
    app.register_blueprint(files_bp)

    # Route-level @login_required decorators guard every page and file
    # response individually (see each blueprint) -- this hook is a second,
    # coarse-grained backstop so a newly added route can never accidentally
    # ship unauthenticated by omission.
    EXEMPT_ENDPOINTS = {"auth.login", "static", "main.llms_txt"}

    # Lets a plain URL-fetch AI tool (no session, no cookies) read gated
    # content via ?token=... instead of a real login -- see
    # User.api_token in app/models.py. Deliberately excludes main.* (the
    # /connect pages and any future account-management routes), so a leaked
    # token can only ever read content, never view or regenerate itself.
    TOKEN_ELIGIBLE_BLUEPRINTS = {"dashboards", "reports", "industry_reports", "topics", "files"}

    @app.before_request
    def enforce_login():
        if request.endpoint in EXEMPT_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            token = request.args.get("token")
            if token and request.blueprint in TOKEN_ELIGIBLE_BLUEPRINTS:
                token_user = User.query.filter_by(api_token=token).first()
                if token_user and token_user.api_token_is_valid():
                    login_user(token_user)
                    token_user.record_api_token_use(request.remote_addr)
                    db.session.commit()
                    return None
            return redirect(url_for("auth.login", next=request.path))
        return None

    @app.after_request
    def set_referrer_policy(response):
        # Query-string tokens can leak via the Referer header if a page ever
        # links out to a third-party URL -- this app never does, but it's a
        # one-line safeguard now that URLs can carry an auth token at all.
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    with app.app_context():
        db.create_all()

    return app
