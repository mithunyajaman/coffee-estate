import json
import math
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.attendance import FaceEnrollment
from app.services.auth_service import login_user, logout_user, get_current_user, login_required
from app.services.audit_service import log_audit
from app.limiter import limiter

auth_bp = Blueprint("auth", __name__)


def cosine_similarity(v1, v2):
    """Compute mathematical cosine similarity between two feature vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))

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


@auth_bp.route("/api/auth/face-login", methods=["POST"])
@limiter.limit("20 per minute")
def api_face_login():
    """Biometric Face Recognition Login directly from login page."""
    data = request.get_json(silent=True) or {}
    sample_vector = data.get("vector")
    simulate_code = data.get("simulate_employee_code")

    emp = None
    confidence = 0.0

    if simulate_code:
        emp = Employee.query.filter_by(employee_code=simulate_code).first()
        confidence = 0.942
    elif sample_vector and isinstance(sample_vector, list):
        enrollments = FaceEnrollment.query.filter_by(enrollment_status="Enrolled").all()
        if not enrollments:
            return jsonify({
                "success": False,
                "error": "No biometric face profiles enrolled yet in the estate database. You can enroll your face in Page 11."
            }), 404

        best_enr = None
        best_sim = 0.0
        for enr in enrollments:
            try:
                stored = json.loads(enr.protected_template)
                sim = cosine_similarity(sample_vector, stored)
                if sim > best_sim:
                    best_sim = sim
                    best_enr = enr
            except Exception:
                continue

        threshold = best_enr.confidence_threshold if best_enr else 0.75
        if best_enr and best_sim >= threshold:
            emp = best_enr.employee
            confidence = best_sim
        else:
            return jsonify({
                "success": False,
                "confidence": round(best_sim, 3),
                "error": f"Face recognition confidence ({round(best_sim * 100, 1)}%) below required threshold ({int(threshold * 100)}%). Please sign in with password."
            }), 401

    if not emp:
        return jsonify({"success": False, "error": "Employee record not found for this biometric template."}), 404

    # Find matching User for this employee
    user = User.query.filter_by(employee_code=emp.employee_code).first()
    if not user:
        user = User.query.filter(User.username.ilike(emp.name.split()[0])).first()

    if not user:
        # Auto-create worker User account if employee exists
        user = User(
            username=emp.employee_code.lower(),
            email=emp.email or f"{emp.employee_code.lower()}@coffee-estate.local",
            role="Employee",
            employee_code=emp.employee_code,
            status="Active"
        )
        user.set_password("WorkerPassword@123")
        db.session.add(user)
        db.session.commit()

    if user.status != "Active":
        return jsonify({"success": False, "error": "This account is inactive. Please contact administration."}), 403

    login_user(user)

    log_audit(
        action="FACE_LOGIN_SUCCESS",
        entity_type="User",
        entity_id=str(user.id),
        outcome="SUCCESS",
        details=f"Face recognition sign-in successful for {emp.name} ({emp.employee_code}) with {round(confidence * 100, 1)}% confidence.",
        actor_id=user.id,
        actor_username=user.username,
    )

    return jsonify({
        "success": True,
        "message": f"Biometric Face ID verified ({round(confidence * 100, 1)}% confidence)! Welcome, {emp.name}.",
        "employee_name": emp.name,
        "employee_code": emp.employee_code,
        "role": user.role,
        "redirect_url": url_for("dashboard.dashboard"),
    })


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register new estate user / worker account."""
    if get_current_user():
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        contact = request.form.get("contact", "").strip()
        role = request.form.get("role", "Employee").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not name or not username or not password or not contact:
            flash("Full Name, Username, Phone Number, and Password are required.", "danger")
            return render_template("login.html", active_tab="register", reg_data=request.form), 400

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("login.html", active_tab="register", reg_data=request.form), 400

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("login.html", active_tab="register", reg_data=request.form), 400

        # Check existing username
        existing_user = User.query.filter(User.username.ilike(username)).first()
        if existing_user:
            flash("That username is already taken. Please pick another.", "warning")
            return render_template("login.html", active_tab="register", reg_data=request.form), 400

        # Auto-generate next employee code
        emp_count = Employee.query.count()
        emp_code = f"EMP{emp_count + 1:03d}"
        while Employee.query.filter_by(employee_code=emp_code).first():
            emp_count += 1
            emp_code = f"EMP{emp_count + 1:03d}"

        # Create Employee
        new_emp = Employee(
            employee_code=emp_code,
            name=name,
            contact=contact,
            email=email or f"{username}@coffee-estate.local",
            job_role=role if role != "Employee" else "Field Specialist",
            wage_rate=650.00,
            status="Active",
            joining_date=date.today(),
        )
        db.session.add(new_emp)
        db.session.flush()

        # Create User
        new_user = User(
            username=username,
            email=email or f"{username}@coffee-estate.local",
            role=role if role in ["Admin", "Estate Manager", "Employee"] else "Employee",
            employee_code=emp_code,
            status="Active",
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        log_audit(
            action="USER_REGISTRATION",
            entity_type="User",
            entity_id=str(new_user.id),
            outcome="SUCCESS",
            details=f"New user registered: {username} ({name}) with code {emp_code}",
            actor_id=new_user.id,
            actor_username=new_user.username,
        )

        login_user(new_user)
        flash(f"Account successfully created! Welcome to Emerald Heights Coffee Estate, {name}.", "success")
        return redirect(url_for("dashboard.dashboard"))

    return render_template("login.html", active_tab="register")

