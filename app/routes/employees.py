from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.database import db
from app.models.employee import Employee
from app.models.user import User
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

employees_bp = Blueprint("employees", __name__)

@employees_bp.route("/employees")
@login_required
def employee_list():
    """Page 10: Employee Register with role-restricted wage and contact views."""
    current_user = get_current_user()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    role_filter = request.args.get("job_role", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Employee.query
    if search:
        query = query.filter(
            (Employee.name.ilike(f"%{search}%")) |
            (Employee.employee_code.ilike(f"%{search}%")) |
            (Employee.contact.ilike(f"%{search}%"))
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    if role_filter:
        query = query.filter_by(job_role=role_filter)

    pagination = query.order_by(Employee.employee_code.asc()).paginate(page=page, per_page=10, error_out=False)
    employees = pagination.items

    distinct_roles = [r[0] for r in db.session.query(Employee.job_role).distinct().all()]

    return render_template(
        "employees.html",
        employees=employees,
        pagination=pagination,
        distinct_roles=distinct_roles,
        search=search,
        status_filter=status_filter,
        role_filter=role_filter,
        current_user=current_user,
    )


@employees_bp.route("/employees/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_employee():
    """Create new employee record."""
    current_user = get_current_user()
    code = (request.form.get("employee_code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    job_role = (request.form.get("job_role") or "").strip()
    wage_str = request.form.get("wage_rate") or "0"
    status = request.form.get("status") or "Active"
    joining_date_str = request.form.get("joining_date") or str(date.today())

    if not code or not name or not contact or not job_role:
        flash("Employee code, name, contact, and job role are required.", "danger")
        return redirect(url_for("employees.employee_list"))

    existing = Employee.query.filter_by(employee_code=code).first()
    if existing:
        flash(f"Employee code '{code}' already in use.", "danger")
        return redirect(url_for("employees.employee_list"))

    try:
        wage_rate = Decimal(wage_str)
        if wage_rate < 0:
            flash("Wage rate cannot be negative.", "danger")
            return redirect(url_for("employees.employee_list"))
    except Exception:
        flash("Invalid wage rate number.", "danger")
        return redirect(url_for("employees.employee_list"))

    try:
        joining_date = datetime.strptime(joining_date_str, "%Y-%m-%d").date()
    except ValueError:
        joining_date = date.today()

    emp = Employee(
        employee_code=code,
        name=name,
        contact=contact,
        email=email,
        job_role=job_role,
        wage_rate=wage_rate,
        status=status,
        joining_date=joining_date,
    )
    db.session.add(emp)
    db.session.commit()

    log_audit(
        action="EMPLOYEE_CREATE",
        entity_type="Employee",
        entity_id=str(emp.id),
        outcome="SUCCESS",
        details=f"Created employee '{emp.employee_code}' ({emp.name}, {emp.job_role}, Wage: {emp.wage_rate})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Employee '{emp.name}' ({emp.employee_code}) added successfully.", "success")
    return redirect(url_for("employees.employee_list"))


@employees_bp.route("/employees/<int:emp_id>/edit", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def edit_employee(emp_id):
    """Update employee details and wage rate."""
    current_user = get_current_user()
    emp = db.session.get(Employee, emp_id)
    if not emp:
        flash("Employee not found.", "danger")
        return redirect(url_for("employees.employee_list"))

    name = (request.form.get("name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    job_role = (request.form.get("job_role") or "").strip()
    wage_str = request.form.get("wage_rate") or str(emp.wage_rate)
    status = request.form.get("status") or emp.status

    if not name or not contact or not job_role:
        flash("Name, contact, and job role cannot be blank.", "danger")
        return redirect(url_for("employees.employee_list"))

    try:
        wage_rate = Decimal(wage_str)
        if wage_rate < 0:
            flash("Wage rate cannot be negative.", "danger")
            return redirect(url_for("employees.employee_list"))
    except Exception:
        flash("Invalid wage rate.", "danger")
        return redirect(url_for("employees.employee_list"))

    old_wage = emp.wage_rate
    emp.name = name
    emp.contact = contact
    emp.email = email
    emp.job_role = job_role
    emp.wage_rate = wage_rate
    emp.status = status
    db.session.commit()

    log_audit(
        action="EMPLOYEE_UPDATE",
        entity_type="Employee",
        entity_id=str(emp.id),
        outcome="SUCCESS",
        details=f"Updated employee {emp.employee_code}. Wage change: {old_wage} -> {wage_rate}. Status: {status}",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Employee '{emp.name}' details updated.", "success")
    return redirect(url_for("employees.employee_list"))
