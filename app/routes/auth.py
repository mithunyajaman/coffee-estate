from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.services.auth_service import login_user, logout_user, get_current_user, login_required
from app.services.audit_service import log_audit
from app.limiter import limiter

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    """Page 2: Login and Authentication."""
    if get_current_user():
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        if not identifier or not password:
            flash("Please enter both your Username/Employee ID and password.", "danger")
            return render_template("login.html", identifier=identifier), 400

        # Query user by username, email, or linked employee_code
        user = User.query.filter(
            or_(
                User.username.ilike(identifier),
                User.email.ilike(identifier),
                User.employee_code.ilike(identifier),
            )
        ).first()

        # If not found directly, also check if identifier matches an employee code and find linked user
        if not user:
            emp = Employee.query.filter(Employee.employee_code.ilike(identifier)).first()
            if emp:
                user = User.query.filter_by(employee_code=emp.employee_code).first()

        if not user or not user.check_password(password):
            log_audit(
                action="LOGIN_FAILURE",
                entity_type="User",
                entity_id=identifier,
                outcome="FAILURE",
                details=f"Invalid credentials attempted for '{identifier}'",
            )
            flash("Invalid credentials. Please verify your Employee ID / Username and password.", "danger")
            return render_template("login.html", identifier=identifier), 401

        if user.status != "Active":
            log_audit(
                action="LOGIN_BLOCKED_INACTIVE",
                entity_type="User",
                entity_id=str(user.id),
                outcome="DENIED",
                details=f"Login attempt for inactive user '{user.username}' (Status: {user.status})",
                actor_id=user.id,
                actor_username=user.username,
            )
            flash("Your account is currently inactive or suspended. Please contact estate administration.", "warning")
            return render_template("login.html", identifier=identifier), 403

        # Success - Login user and establish server session
        login_user(user)

        next_page = request.args.get("next")
        # Validate next_page to prevent open redirect
        if not next_page or not next_page.startswith("/"):
            next_page = url_for("dashboard.dashboard")

        flash(f"Welcome back, {user.username}! Signed in as {user.role}.", "success")
        return redirect(next_page)

    return render_template("login.html")


@auth_bp.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def api_login():
    """API endpoint for login."""
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "Username/Employee ID and password are required"}), 400

    user = User.query.filter(
        or_(
            User.username.ilike(identifier),
            User.email.ilike(identifier),
            User.employee_code.ilike(identifier),
        )
    ).first()

    if not user:
        emp = Employee.query.filter(Employee.employee_code.ilike(identifier)).first()
        if emp:
            user = User.query.filter_by(employee_code=emp.employee_code).first()

    if not user or not user.check_password(password):
        log_audit(
            action="API_LOGIN_FAILURE",
            entity_type="User",
            entity_id=identifier,
            outcome="FAILURE",
            details=f"API login failure for '{identifier}'",
        )
        return jsonify({"error": "Invalid username or password"}), 401

    if user.status != "Active":
        return jsonify({"error": "Account is inactive or suspended"}), 403

    login_user(user)
    return jsonify({
        "message": "Login successful",
        "user": user.to_dict(),
        "redirect_url": url_for("dashboard.dashboard"),
    })


@auth_bp.route("/logout")
def logout():
    """User logout."""
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"message": "Successfully logged out"})


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password request workflow."""
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        # Always return a generic success notice to prevent account enumeration
        if identifier:
            user = User.query.filter(
                or_(User.username.ilike(identifier), User.email.ilike(identifier))
            ).first()
            if user:
                log_audit(
                    action="PASSWORD_RESET_REQUEST",
                    entity_type="User",
                    entity_id=str(user.id),
                    outcome="SUCCESS",
                    details=f"Password reset initiated for {user.username}",
                    actor_id=user.id,
                    actor_username=user.username,
                )
            else:
                log_audit(
                    action="PASSWORD_RESET_ATTEMPT_UNKNOWN",
                    entity_type="User",
                    entity_id=identifier,
                    outcome="FAILURE",
                    details=f"Password reset requested for non-existent '{identifier}'",
                )

        flash(
            "If an account matches your Employee ID or email, instructions to reset your password have been sent to your administrator.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")
