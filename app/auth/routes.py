from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..errors import AppError, ValidationError
from ..security import is_safe_redirect
from . import bp

# Where signed-in users land.
HOME_ENDPOINT = "scans.index"
from .services import authenticate, register_user


def _after_login_target() -> str:
    target = request.args.get("next") or request.form.get("next")
    return target if is_safe_redirect(target) else url_for(HOME_ENDPOINT)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(HOME_ENDPOINT))
    form, errors, status = {}, {}, 200
    if request.method == "POST":
        form = {k: request.form.get(k, "") for k in ("username", "email")}
        try:
            user = register_user(form["username"], form["email"],
                                 request.form.get("password", ""), request.form.get("confirm", ""))
        except ValidationError as err:
            errors, status = err.details["fields"], 422
        except AppError as err:
            flash(err.message, "error")
            status = err.status_code
        else:
            login_user(user)
            flash(f"Welcome, {user.username}! Your account is ready.", "success")
            return redirect(url_for(HOME_ENDPOINT))
    return render_template("auth/register.html", form=form, errors=errors), status


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(HOME_ENDPOINT))
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "")
        user = authenticate(username, request.form.get("password", ""))
        if user:
            login_user(user, remember=bool(request.form.get("remember")))
            flash("Signed in.", "success")
            return redirect(_after_login_target())
        flash("Invalid username or password.", "error")
        return render_template("auth/login.html", username=username), 401
    return render_template("auth/login.html", username=username)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))
