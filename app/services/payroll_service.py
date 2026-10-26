from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Dict, Any, Tuple, List
from app.database import db
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.payroll import PayrollRecord, SalaryAdvance

def calculate_attendance_summary(employee_id: int, start_date: date, end_date: date) -> Tuple[float, int, int, int, List[Dict[str, Any]]]:
    """Queries DailyAttendance records for an employee within a given date range.
    
    Rule:
    - Present: 1.0 payable day
    - Half-day: 0.5 payable day
    - Absent / On Leave / Other: 0.0 payable day
    
    Returns:
    (payable_days, present_days, half_days, absent_days, attendance_trace_list)
    """
    records = (
        DailyAttendance.query.filter(
            DailyAttendance.employee_id == employee_id,
            DailyAttendance.date >= start_date,
            DailyAttendance.date <= end_date,
        )
        .order_by(DailyAttendance.date.asc())
        .all()
    )

    present_count = 0
    half_day_count = 0
    absent_count = 0
    trace_list = []

    for r in records:
        day_credit = 0.0
        if r.status == "Present":
            present_count += 1
            day_credit = 1.0
        elif r.status == "Half-day":
            half_day_count += 1
            day_credit = 0.5
        else:
            absent_count += 1
            day_credit = 0.0

        trace_list.append({
            "id": r.id,
            "date": r.date.isoformat(),
            "shift": r.shift,
            "status": r.status,
            "day_credit": day_credit,
            "approved_by": r.approved_by,
        })

    payable_days = float(present_count * 1.0 + half_day_count * 0.5)
    return payable_days, present_count, half_day_count, absent_count, trace_list


def generate_payroll_record(
    employee_id: int,
    start_date: date,
    end_date: date,
    period_label: str,
    overtime_hours: float = 0.0,
    overtime_rate: float = 0.0,
    advances_amount: float = 0.0,
    deductions_amount: float = 0.0,
    generated_by: str = None,
    notes: str = None,
) -> PayrollRecord:
    """Computes and creates or updates a PayrollRecord for the given employee and period.
    
    Formula strictly implements:
    Gross = (Payable Days × Daily Wage) + Approved Overtime
    Net = Gross − Advances − Deductions
    """
    employee = Employee.query.get_or_404(employee_id)
    daily_wage = float(employee.wage_rate or 0.0)

    # 1. Attendance trace
    payable_days, present_days, half_days, absent_days, _ = calculate_attendance_summary(
        employee_id, start_date, end_date
    )

    # 2. Overtime calculation
    ot_hours = float(overtime_hours or 0.0)
    ot_rate = float(overtime_rate or 0.0)
    if ot_rate <= 0.0 and ot_hours > 0.0:
        # Default standard overtime formula: 1.5x hourly wage assuming 8-hour shift
        hourly = daily_wage / 8.0 if daily_wage > 0 else 0.0
        ot_rate = round(hourly * 1.5, 2)
    
    ot_pay = round(ot_hours * ot_rate, 2)

    # 3. Sum advances if not explicitly overridden
    adv_val = float(advances_amount or 0.0)
    if adv_val <= 0.0:
        pending_advances = SalaryAdvance.query.filter(
            SalaryAdvance.employee_id == employee_id,
            SalaryAdvance.request_date >= start_date,
            SalaryAdvance.request_date <= end_date,
            SalaryAdvance.status.in_(["Approved", "Pending"]),
        ).all()
        adv_val = sum(float(a.amount) for a in pending_advances)

    ded_val = float(deductions_amount or 0.0)

    # 4. Gross and Net computation
    gross_pay = round((payable_days * daily_wage) + ot_pay, 2)
    net_pay = round(gross_pay - adv_val - ded_val, 2)

    # Check for existing record in this period
    record = PayrollRecord.query.filter_by(
        employee_id=employee_id,
        period_start=start_date,
        period_end=end_date,
    ).first()

    if not record:
        record = PayrollRecord(
            employee_id=employee_id,
            period_start=start_date,
            period_end=end_date,
            period_label=period_label,
            daily_wage=daily_wage,
            payable_days=payable_days,
            present_days=present_days,
            half_days=half_days,
            absent_days=absent_days,
            overtime_hours=ot_hours,
            overtime_rate=ot_rate,
            overtime_pay=ot_pay,
            gross_pay=gross_pay,
            advances=adv_val,
            deductions=ded_val,
            net_pay=net_pay,
            status="Draft",
            generated_by=generated_by,
            notes=notes,
        )
        db.session.add(record)
    else:
        # Update existing draft
        if record.status in ["Draft", "Cancelled"]:
            record.period_label = period_label
            record.daily_wage = daily_wage
            record.payable_days = payable_days
            record.present_days = present_days
            record.half_days = half_days
            record.absent_days = absent_days
            record.overtime_hours = ot_hours
            record.overtime_rate = ot_rate
            record.overtime_pay = ot_pay
            record.gross_pay = gross_pay
            record.advances = adv_val
            record.deductions = ded_val
            record.net_pay = net_pay
            record.notes = notes
            record.generated_by = generated_by

    db.session.commit()

    # Link advances to this record
    advances_to_link = SalaryAdvance.query.filter(
        SalaryAdvance.employee_id == employee_id,
        SalaryAdvance.request_date >= start_date,
        SalaryAdvance.request_date <= end_date,
        SalaryAdvance.status.in_(["Approved", "Pending"]),
    ).all()
    for adv in advances_to_link:
        adv.payroll_record_id = record.id
        adv.status = "Deducted"
    db.session.commit()

    return record
