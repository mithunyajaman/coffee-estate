import csv
import io
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, request, Response, abort, jsonify
from sqlalchemy import func
from app.database import db
from app.services.auth_service import login_required, get_current_user
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.harvest import HarvestRecord
from app.models.farm import EstateBlock
from app.models.inventory import InventoryItem, StockTransaction
from app.models.payroll import PayrollRecord
from app.services.audit_service import log_audit

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def parse_date_filters():
    """Parses date range filters from request args, defaulting to current month."""
    today = date.today()
    preset = request.args.get("preset", "")
    
    if preset == "today":
        start_date = today
        end_date = today
    elif preset == "7days":
        start_date = today - timedelta(days=6)
        end_date = today
    elif preset == "30days":
        start_date = today - timedelta(days=29)
        end_date = today
    elif preset == "ytd":
        start_date = date(today.year, 1, 1)
        end_date = today
    else:
        # Default or custom
        start_str = request.args.get("start_date")
        end_str = request.args.get("end_date")
        if start_str and end_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                start_date = today.replace(day=1)
                end_date = today
        else:
            preset = "month"
            start_date = today.replace(day=1)
            end_date = today

    return start_date, end_date, preset


@reports_bp.route("/", methods=["GET"])
@login_required
def index():
    user = get_current_user()
    start_date, end_date, preset = parse_date_filters()

    # 1. Attendance Metrics
    att_query = DailyAttendance.query.filter(
        DailyAttendance.date >= start_date,
        DailyAttendance.date <= end_date,
    )
    if not user.is_manager:
        emp = Employee.query.filter_by(employee_code=user.employee_code).first()
        if emp:
            att_query = att_query.filter(DailyAttendance.employee_id == emp.id)
        else:
            att_query = att_query.filter(DailyAttendance.id == -1)

    attendance_records = att_query.order_by(DailyAttendance.date.asc()).all()

    # Aggregate daily attendance for Chart.js
    daily_att_map = {}
    total_present = 0
    total_half_day = 0
    total_absent = 0

    curr = start_date
    while curr <= end_date:
        daily_att_map[curr.isoformat()] = {"date": curr.strftime("%d %b"), "present": 0, "half_day": 0, "absent": 0}
        curr += timedelta(days=1)

    for att in attendance_records:
        ds = att.date.isoformat()
        if ds in daily_att_map:
            if att.status == "Present":
                daily_att_map[ds]["present"] += 1
                total_present += 1
            elif att.status == "Half-day":
                daily_att_map[ds]["half_day"] += 1
                total_half_day += 1
            else:
                daily_att_map[ds]["absent"] += 1
                total_absent += 1

    # 2. Harvest Metrics
    harvest_query = HarvestRecord.query.filter(
        HarvestRecord.date >= start_date,
        HarvestRecord.date <= end_date,
    )
    harvest_records = harvest_query.order_by(HarvestRecord.date.desc()).all()
    total_harvest_kg = sum(float(h.actual_quantity) for h in harvest_records)

    # Harvest by Block
    harvest_by_block = {}
    for h in harvest_records:
        b_name = h.block.name if h.block else "General / Unassigned"
        harvest_by_block[b_name] = harvest_by_block.get(b_name, 0.0) + float(h.actual_quantity)

    # 3. Inventory Stock Metrics
    inventory_items = InventoryItem.query.order_by(InventoryItem.name.asc()).all()
    low_stock_items = [item for item in inventory_items if item.is_low_stock]
    
    # 4. Payroll Metrics (Manager / Admin only)
    total_payroll_gross = 0.0
    total_payroll_net = 0.0
    total_payroll_deductions = 0.0
    payroll_by_period = {}

    if user.is_manager:
        payroll_records = PayrollRecord.query.filter(
            PayrollRecord.period_start >= start_date,
            PayrollRecord.period_end <= end_date,
        ).all()
        # If no records in exact window, fallback to records intersecting window
        if not payroll_records:
            payroll_records = PayrollRecord.query.order_by(PayrollRecord.period_start.desc()).limit(20).all()

        total_payroll_gross = sum(float(p.gross_pay) for p in payroll_records)
        total_payroll_net = sum(float(p.net_pay) for p in payroll_records)
        total_payroll_deductions = sum(float(p.deductions) + float(p.advances) for p in payroll_records)

        for p in payroll_records:
            lbl = p.period_label
            if lbl not in payroll_by_period:
                payroll_by_period[lbl] = {"gross": 0.0, "net": 0.0, "deductions": 0.0}
            payroll_by_period[lbl]["gross"] += float(p.gross_pay)
            payroll_by_period[lbl]["net"] += float(p.net_pay)
            payroll_by_period[lbl]["deductions"] += float(p.deductions) + float(p.advances)

    summary = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "preset": preset,
        "total_attendance_records": len(attendance_records),
        "total_present": total_present,
        "total_half_day": total_half_day,
        "total_absent": total_absent,
        "total_harvest_kg": round(total_harvest_kg, 2),
        "total_harvest_batches": len(harvest_records),
        "total_inventory_items": len(inventory_items),
        "low_stock_count": len(low_stock_items),
        "total_payroll_gross": total_payroll_gross,
        "total_payroll_net": total_payroll_net,
        "total_payroll_deductions": total_payroll_deductions,
    }

    # Prepare chart payload
    chart_data = {
        "attendance_dates": [v["date"] for v in daily_att_map.values()],
        "attendance_present": [v["present"] for v in daily_att_map.values()],
        "attendance_half_day": [v["half_day"] for v in daily_att_map.values()],
        "attendance_absent": [v["absent"] for v in daily_att_map.values()],
        "harvest_block_labels": list(harvest_by_block.keys()),
        "harvest_block_values": [round(v, 2) for v in harvest_by_block.values()],
        "inventory_labels": [item.name for item in inventory_items[:8]],
        "inventory_current": [float(item.current_balance) for item in inventory_items[:8]],
        "inventory_min": [float(item.reorder_level) for item in inventory_items[:8]],
        "payroll_periods": list(payroll_by_period.keys()),
        "payroll_gross": [round(v["gross"], 2) for v in payroll_by_period.values()],
        "payroll_net": [round(v["net"], 2) for v in payroll_by_period.values()],
    }

    return render_template(
        "reports.html",
        is_manager=user.is_manager,
        summary=summary,
        chart_data=chart_data,
        harvest_records=harvest_records[:15],
        low_stock_items=low_stock_items,
        inventory_items=inventory_items,
    )


@reports_bp.route("/export/csv", methods=["GET"])
@login_required
def export_csv():
    user = get_current_user()
    export_type = request.args.get("type", "attendance")
    start_date, end_date, _ = parse_date_filters()

    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == "attendance":
        writer.writerow(["ID", "Employee Code", "Employee Name", "Date", "Shift", "Status", "Approved By", "Conflict"])
        att_query = DailyAttendance.query.filter(DailyAttendance.date >= start_date, DailyAttendance.date <= end_date)
        if not user.is_manager:
            emp = Employee.query.filter_by(employee_code=user.employee_code).first()
            if emp:
                att_query = att_query.filter(DailyAttendance.employee_id == emp.id)
            else:
                att_query = att_query.filter(DailyAttendance.id == -1)
        for r in att_query.order_by(DailyAttendance.date.asc()).all():
            writer.writerow([
                r.id,
                r.employee.employee_code if r.employee else "",
                r.employee.name if r.employee else "",
                r.date.isoformat(),
                r.shift,
                r.status,
                r.approved_by or "",
                "Yes" if r.has_conflict else "No",
            ])
        filename = f"attendance_report_{start_date}_{end_date}.csv"

    elif export_type == "harvest":
        writer.writerow(["ID", "Date", "Block", "Planned (kg)", "Actual (kg)", "Variance (kg)", "Team", "Processing Status", "Notes"])
        harvest_records = HarvestRecord.query.filter(
            HarvestRecord.date >= start_date,
            HarvestRecord.date <= end_date,
        ).order_by(HarvestRecord.date.asc()).all()
        for h in harvest_records:
            writer.writerow([
                h.id,
                h.date.isoformat(),
                h.block.name if h.block else "",
                float(h.planned_quantity),
                float(h.actual_quantity),
                float(h.variance_kg),
                h.team_id or "",
                h.processing_status or "",
                h.notes or "",
            ])
        filename = f"harvest_report_{start_date}_{end_date}.csv"

    elif export_type == "inventory":
        writer.writerow(["Item ID", "Name", "Category", "Current Stock", "Unit", "Reorder Level", "Low Stock Alert"])
        items = InventoryItem.query.order_by(InventoryItem.name.asc()).all()
        for item in items:
            writer.writerow([
                item.id,
                item.name,
                item.category,
                float(item.current_balance),
                item.unit,
                float(item.reorder_level),
                "LOW STOCK" if item.is_low_stock else "Normal",
            ])
        filename = f"inventory_status_{date.today().isoformat()}.csv"

    elif export_type == "payroll":
        # Strict permission check: only managers and admin may export payroll
        if not user.is_manager:
            abort(403)
        writer.writerow([
            "Slip ID", "Employee Code", "Employee Name", "Job Role", "Period", "Start Date", "End Date",
            "Daily Wage", "Payable Days", "Present Days", "Half Days", "Absent Days",
            "Overtime Pay", "Gross Wages", "Advances Deducted", "Other Deductions", "Net Disbursed",
            "Status", "Payment Method", "Reference", "Approved By"
        ])
        records = PayrollRecord.query.filter(
            PayrollRecord.period_start >= start_date,
            PayrollRecord.period_end <= end_date,
        ).order_by(PayrollRecord.period_start.asc(), PayrollRecord.id.asc()).all()
        if not records:
            records = PayrollRecord.query.order_by(PayrollRecord.id.desc()).all()
            
        for p in records:
            writer.writerow([
                p.id,
                p.employee.employee_code if p.employee else "",
                p.employee.name if p.employee else "",
                p.employee.job_role if p.employee else "",
                p.period_label,
                p.period_start.isoformat(),
                p.period_end.isoformat(),
                float(p.daily_wage),
                float(p.payable_days),
                p.present_days,
                p.half_days,
                p.absent_days,
                float(p.overtime_pay),
                float(p.gross_pay),
                float(p.advances),
                float(p.deductions),
                float(p.net_pay),
                p.status,
                p.payment_method,
                p.payment_reference or "",
                p.approved_by or "",
            ])
        filename = f"estate_payroll_ledger_{start_date}_{end_date}.csv"

    else:
        abort(400)

    log_audit(
        action="REPORT_CSV_EXPORT",
        entity_type="Report",
        entity_id=None,
        outcome="SUCCESS",
        details=f"Exported CSV report type '{export_type}' for date range {start_date} to {end_date}",
        actor_id=user.id,
        actor_username=user.username,
    )

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
