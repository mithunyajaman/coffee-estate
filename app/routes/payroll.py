from datetime import datetime, timezone, date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from app.database import db
from app.services.auth_service import login_required, manager_required, get_current_user
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.payroll import PayrollRecord, SalaryAdvance
from app.services.audit_service import log_audit
from app.services.payroll_service import calculate_attendance_summary, generate_payroll_record

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")


@payroll_bp.route("/", methods=["GET"])
@login_required
def index():
    user = get_current_user()
    
    # 1. Non-managers only see their own payslips
    if not user.is_manager:
        emp = Employee.query.filter_by(employee_code=user.employee_code).first()
        my_records = []
        my_advances = []
        if emp:
            my_records = PayrollRecord.query.filter_by(employee_id=emp.id).order_by(PayrollRecord.period_start.desc()).all()
            my_advances = SalaryAdvance.query.filter_by(employee_id=emp.id).order_by(SalaryAdvance.request_date.desc()).all()
        return render_template(
            "payroll.html",
            is_manager=False,
            employee=emp,
            payroll_records=my_records,
            advances=my_advances,
            summary={
                "total_records": len(my_records),
                "total_net_received": sum(float(r.net_pay) for r in my_records if r.status == "Disbursed"),
                "latest_record": my_records[0] if my_records else None,
            }
        )

    # 2. Manager / Admin View
    employees = Employee.query.filter_by(status="Active").order_by(Employee.name.asc()).all()
    selected_status = request.args.get("status", "")
    
    query = PayrollRecord.query
    if selected_status:
        query = query.filter(PayrollRecord.status == selected_status)
    payroll_records = query.order_by(PayrollRecord.period_start.desc(), PayrollRecord.id.desc()).all()
    
    advances = SalaryAdvance.query.order_by(SalaryAdvance.request_date.desc()).limit(30).all()

    # Calculations for summary widgets
    total_gross = sum(float(r.gross_pay) for r in payroll_records)
    total_net = sum(float(r.net_pay) for r in payroll_records)
    total_deductions = sum(float(r.deductions) + float(r.advances) for r in payroll_records)
    pending_approval_count = sum(1 for r in payroll_records if r.status == "Draft")

    summary = {
        "total_records": len(payroll_records),
        "total_gross": total_gross,
        "total_net": total_net,
        "total_deductions": total_deductions,
        "pending_approval_count": pending_approval_count,
    }

    # Default date range for the payroll generation modal: current month
    today = date.today()
    default_start = today.replace(day=1)
    # last day of month
    if today.month == 12:
        default_end = date(today.year, 12, 31)
    else:
        next_month = date(today.year, today.month + 1, 1)
        default_end = date.fromordinal(next_month.toordinal() - 1)
    default_period_label = today.strftime("%B %Y")

    return render_template(
        "payroll.html",
        is_manager=True,
        employees=employees,
        payroll_records=payroll_records,
        advances=advances,
        summary=summary,
        selected_status=selected_status,
        default_start=default_start.isoformat(),
        default_end=default_end.isoformat(),
        default_period_label=default_period_label,
    )


@payroll_bp.route("/generate", methods=["POST"])
@login_required
@manager_required
def generate():
    user = get_current_user()
    emp_target = request.form.get("employee_id")
    period_start_raw = request.form.get("period_start")
    period_end_raw = request.form.get("period_end")
    period_label = request.form.get("period_label", "").strip()
    notes = request.form.get("notes", "").strip()

    if not period_start_raw or not period_end_raw or not period_label:
        flash("Period start date, end date, and period label are required.", "danger")
        return redirect(url_for("payroll.index"))

    try:
        start_date = datetime.strptime(period_start_raw, "%Y-%m-%d").date()
        end_date = datetime.strptime(period_end_raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format. Use YYYY-MM-DD.", "danger")
        return redirect(url_for("payroll.index"))

    if start_date > end_date:
        flash("Period start date cannot be after end date.", "danger")
        return redirect(url_for("payroll.index"))

    overtime_hours = float(request.form.get("overtime_hours") or 0.0)
    overtime_rate = float(request.form.get("overtime_rate") or 0.0)
    advances_amount = float(request.form.get("advances_amount") or 0.0)
    deductions_amount = float(request.form.get("deductions_amount") or 0.0)

    generated_count = 0
    if emp_target == "all":
        # Batch generation for all active employees
        active_employees = Employee.query.filter_by(status="Active").all()
        for emp in active_employees:
            generate_payroll_record(
                employee_id=emp.id,
                start_date=start_date,
                end_date=end_date,
                period_label=period_label,
                overtime_hours=0.0,
                overtime_rate=0.0,
                advances_amount=0.0, # Will auto-sum pending advances for each employee
                deductions_amount=0.0,
                generated_by=user.username,
                notes=notes or "Batch generated payroll",
            )
            generated_count += 1
        log_audit(
            action="PAYROLL_BATCH_GENERATE",
            entity_type="PayrollRecord",
            entity_id=None,
            outcome="SUCCESS",
            details=f"Batch generated payroll for {generated_count} active employees for {period_label} ({start_date} to {end_date})",
            actor_id=user.id,
            actor_username=user.username,
        )
        flash(f"Successfully generated payroll records for {generated_count} active employees.", "success")
    else:
        # Single employee generation
        emp_id = int(emp_target)
        emp = Employee.query.get_or_404(emp_id)
        record = generate_payroll_record(
            employee_id=emp.id,
            start_date=start_date,
            end_date=end_date,
            period_label=period_label,
            overtime_hours=overtime_hours,
            overtime_rate=overtime_rate,
            advances_amount=advances_amount,
            deductions_amount=deductions_amount,
            generated_by=user.username,
            notes=notes,
        )
        log_audit(
            action="PAYROLL_GENERATE",
            entity_type="PayrollRecord",
            entity_id=str(record.id),
            outcome="SUCCESS",
            details=f"Generated payroll for {emp.name} ({emp.employee_code}) for {period_label}: Gross=INR {record.gross_pay}, Net=INR {record.net_pay}",
            actor_id=user.id,
            actor_username=user.username,
        )
        flash(f"Payroll record generated for {emp.name}: Net Pay = ₹{record.net_pay:,.2f}", "success")

    return redirect(url_for("payroll.index"))


@payroll_bp.route("/approve/<int:record_id>", methods=["POST"])
@login_required
@manager_required
def approve(record_id):
    user = get_current_user()
    record = PayrollRecord.query.get_or_404(record_id)
    record.status = "Approved"
    record.approved_by = user.username
    record.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    log_audit(
        action="PAYROLL_APPROVE",
        entity_type="PayrollRecord",
        entity_id=str(record.id),
        outcome="SUCCESS",
        details=f"Approved payroll ID #{record.id} for {record.employee.name} ({record.period_label}). Net: INR {record.net_pay}",
        actor_id=user.id,
        actor_username=user.username,
    )
    flash(f"Payroll record #{record.id} for {record.employee.name} approved.", "success")
    return redirect(url_for("payroll.index"))


@payroll_bp.route("/disburse/<int:record_id>", methods=["POST"])
@login_required
@manager_required
def disburse(record_id):
    user = get_current_user()
    record = PayrollRecord.query.get_or_404(record_id)
    payment_method = request.form.get("payment_method", "Bank Transfer")
    payment_reference = request.form.get("payment_reference", "").strip()

    record.status = "Disbursed"
    record.payment_method = payment_method
    record.payment_reference = payment_reference or f"TXN-{datetime.now().strftime('%Y%m%d%H%M')}-{record.id}"
    record.disbursed_at = datetime.now(timezone.utc)
    db.session.commit()

    log_audit(
        action="PAYROLL_DISBURSE",
        entity_type="PayrollRecord",
        entity_id=str(record.id),
        outcome="SUCCESS",
        details=f"Disbursed payroll ID #{record.id} for {record.employee.name}. Ref: {record.payment_reference}",
        actor_id=user.id,
        actor_username=user.username,
    )
    flash(f"Payroll marked as Disbursed with reference {record.payment_reference}.", "success")
    return redirect(url_for("payroll.index"))


@payroll_bp.route("/advances/create", methods=["POST"])
@login_required
@manager_required
def create_advance():
    user = get_current_user()
    employee_id = request.form.get("employee_id")
    amount_raw = request.form.get("amount")
    reason = request.form.get("reason", "").strip()
    request_date_raw = request.form.get("request_date")

    if not employee_id or not amount_raw or not reason:
        flash("Employee, amount, and reason are required.", "danger")
        return redirect(url_for("payroll.index"))

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash("Amount must be a positive number.", "danger")
        return redirect(url_for("payroll.index"))

    req_date = date.today()
    if request_date_raw:
        try:
            req_date = datetime.strptime(request_date_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    advance = SalaryAdvance(
        employee_id=int(employee_id),
        amount=amount,
        request_date=req_date,
        reason=reason,
        status="Approved",
        approved_by=user.username,
    )
    db.session.add(advance)
    db.session.commit()

    emp = Employee.query.get(employee_id)
    log_audit(
        action="SALARY_ADVANCE_CREATE",
        entity_type="SalaryAdvance",
        entity_id=str(advance.id),
        outcome="SUCCESS",
        details=f"Issued advance of INR {amount:,.2f} to {emp.name if emp else employee_id} for: {reason}",
        actor_id=user.id,
        actor_username=user.username,
    )
    flash(f"Advance of ₹{amount:,.2f} recorded for {emp.name if emp else 'employee'}.", "success")
    return redirect(url_for("payroll.index"))


@payroll_bp.route("/slip/<int:record_id>", methods=["GET"])
@login_required
def salary_slip(record_id):
    user = get_current_user()
    record = PayrollRecord.query.get_or_404(record_id)

    # Scoping check: Field Workers can only view their own slip
    if not user.is_manager:
        if not user.employee_code or record.employee.employee_code != user.employee_code:
            abort(403)

    # Trace attendance records for this period
    _, _, _, _, attendance_trace = calculate_attendance_summary(
        record.employee_id, record.period_start, record.period_end
    )

    return render_template(
        "salary_slip.html",
        record=record,
        employee=record.employee,
        attendance_trace=attendance_trace,
        sample_watermark=True,
    )


@payroll_bp.route("/api/trace/<int:record_id>", methods=["GET"])
@login_required
def trace_attendance(record_id):
    user = get_current_user()
    record = PayrollRecord.query.get_or_404(record_id)
    if not user.is_manager:
        if not user.employee_code or record.employee.employee_code != user.employee_code:
            return jsonify({"success": False, "error": "Access denied"}), 403

    payable_days, present_days, half_days, absent_days, trace_list = calculate_attendance_summary(
        record.employee_id, record.period_start, record.period_end
    )

    return jsonify({
        "success": True,
        "employee_name": record.employee.name,
        "employee_code": record.employee.employee_code,
        "period_label": record.period_label,
        "payable_days": payable_days,
        "present_days": present_days,
        "half_days": half_days,
        "absent_days": absent_days,
        "trace": trace_list,
    })
