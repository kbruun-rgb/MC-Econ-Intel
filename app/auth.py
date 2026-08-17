from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from app import db
from app.models import ActivityEvent, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            db.session.add(ActivityEvent(user_id=user.id, event_type="login"))
            db.session.commit()
            next_path = request.args.get("next")
            if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
                next_path = url_for("main.home")
            return redirect(next_path)
        flash("Incorrect email or password.")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
