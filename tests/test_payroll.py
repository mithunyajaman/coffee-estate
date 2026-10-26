from datetime import date, timedelta
from app.database import db
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.payroll import PayrollRecord, SalaryAdvance
from app.services.payroll_service import calculate_attendance_summary, generate_payroll_record

def test_payroll_calculation_known_numbers(app):
    """Verifies wage formula:
    Gross = (Payable Days * Daily Wage) + Approved Overtime
    Net = Gross - Advances - Deductions
    using strict known numbers.
    """
    with app.app_context():
        emp = Employee.query.filter_by(employee_code="EMP001").first()
        record = PayrollRecord(
            employee_id=emp.id,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            period_label="October 2026",
            daily_wage=650.00,
            payable_days=22.5,
            present_days=21,
            half_days=3,
            absent_days=2,
            overtime_hours=10.0,
            overtime_rate=120.00,
            overtime_pay=1200.00,
            advances=1500.00,
            deductions=500.00,
        )
        gross, net = record.calculate_totals()

        # Expected:
        # Gross = (22.5 * 650.00) + 1200.00 = 14625.00 + 1200.00 = 15825.00
        # Net = 15825.00 - 1500.00 - 500.00 = 13825.00
        assert gross == 15825.00
        assert net == 13825.00
        assert float(record.gross_pay) == 15825.00
        assert float(record.net_pay) == 13825.00


def test_attendance_summary_tracing(app):
    """Verifies that payable days strictly trace to verified attendance records:
    Present = 1.0 day, Half-day = 0.5 day, Absent = 0.0 day.
    """
    with app.app_context():
        emp = Employee.query.filter_by(employee_code="EMP001").first()
        start = date(2026, 10, 1)

        # 10 Present days, 3 Half-days, 2 Absent days = 15 total days
        # Payable days = 10*1.0 + 3*0.5 = 11.5 days
        for i in range(10):
            db.session.add(DailyAttendance(
                employee_id=emp.id,
                date=start + timedelta(days=i),
                shift="Morning Shift",
                status="Present",
                approved_by="Manager Deepak"
            ))
        for i in range(10, 13):
            db.session.add(DailyAttendance(
                employee_id=emp.id,
                date=start + timedelta(days=i),
                shift="Morning Shift",
                status="Half-day",
                approved_by="Manager Deepak"
            ))
        for i in range(13, 15):
            db.session.add(DailyAttendance(
                employee_id=emp.id,
                date=start + timedelta(days=i),
                shift="Morning Shift",
                status="Absent",
                approved_by="Manager Deepak"
            ))
        db.session.commit()

        end = start + timedelta(days=14)
        payable_days, present_days, half_days, absent_days, trace_list = calculate_attendance_summary(
            emp.id, start, end
        )

        assert present_days == 10
        assert half_days == 3
        assert absent_days == 2
        assert payable_days == 11.5
        assert len(trace_list) == 15
        assert trace_list[0]["day_credit"] == 1.0
        assert trace_list[10]["day_credit"] == 0.5
        assert trace_list[13]["day_credit"] == 0.0


def test_manager_payroll_generation_and_approval(client, auth_client, app):
    """Tests Manager ability to generate payroll, verify totals, approve, and disburse."""
    auth_client.login_manager()

    with app.app_context():
        emp = Employee.query.filter_by(employee_code="EMP001").first()
        emp_id = emp.id
        # Seed 5 present days for EMP001
        for i in range(5):
            db.session.add(DailyAttendance(
                employee_id=emp_id,
                date=date(2026, 10, 1) + timedelta(days=i),
                shift="Morning Shift",
                status="Present"
            ))
        db.session.commit()

    # Generate payroll
    resp = client.post("/payroll/generate", data={
        "employee_id": str(emp_id),
        "period_start": "2026-10-01",
        "period_end": "2026-10-15",
        "period_label": "First Half Oct 2026",
        "overtime_hours": "4.0",
        "overtime_rate": "100.0",
        "advances_amount": "500.0",
        "deductions_amount": "150.0",
        "notes": "Verified muster",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        record = PayrollRecord.query.filter_by(employee_id=emp_id, period_start=date(2026, 10, 1)).first()
        assert record is not None
        assert record.status == "Draft"
        # 5 days * 650.0 = 3250.0
        # Overtime: 4 hrs * 100.0 = 400.0
        # Gross = 3650.0
        # Net = 3650.0 - 500.0 - 150.0 = 3000.0
        assert float(record.gross_pay) == 3650.00
        assert float(record.net_pay) == 3000.00

        record_id = record.id

    # Approve record
    resp_appr = client.post(f"/payroll/approve/{record_id}", follow_redirects=True)
    assert resp_appr.status_code == 200

    with app.app_context():
        rec = db.session.get(PayrollRecord, record_id)
        assert rec.status == "Approved"
        assert rec.approved_by == "manager"

    # Disburse record
    resp_disb = client.post(f"/payroll/disburse/{record_id}", data={
        "payment_method": "UPI",
        "payment_reference": "UPI-OCT-4921",
    }, follow_redirects=True)
    assert resp_disb.status_code == 200

    with app.app_context():
        rec = db.session.get(PayrollRecord, record_id)
        assert rec.status == "Disbursed"
        assert rec.payment_reference == "UPI-OCT-4921"


def test_employee_rbac_and_slip_security(client, auth_client, app):
    """Verifies that Employees can view their own salary slip, but cannot approve,
    generate, or view other employees' salary slips.
    """
    # Manager generates two slips: one for EMP001 (Ramesh) and one for ADM001 (Vikram)
    with app.app_context():
        emp1 = Employee.query.filter_by(employee_code="EMP001").first()
        emp_adm = Employee.query.filter_by(employee_code="ADM001").first()

        rec1 = PayrollRecord(
            employee_id=emp1.id,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            period_label="October 2026",
            daily_wage=650.00,
            payable_days=20.0,
            gross_pay=13000.00,
            net_pay=13000.00,
            status="Approved"
        )
        rec_other = PayrollRecord(
            employee_id=emp_adm.id,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            period_label="October 2026",
            daily_wage=2500.00,
            payable_days=20.0,
            gross_pay=50000.00,
            net_pay=50000.00,
            status="Approved"
        )
        db.session.add_all([rec1, rec_other])
        db.session.commit()
        rec1_id = rec1.id
        rec_other_id = rec_other.id

    # Login as field worker (employee)
    auth_client.login_employee()

    # 1. Can view own payroll page
    resp = client.get("/payroll/")
    assert resp.status_code == 200
    assert b"My Payslips" in resp.data

    # 2. Cannot generate payroll -> 403 Forbidden
    resp_gen = client.post("/payroll/generate", data={"employee_id": "1", "period_label": "Test"})
    assert resp_gen.status_code == 403

    # 3. Cannot approve payroll -> 403 Forbidden
    resp_appr = client.post(f"/payroll/approve/{rec1_id}")
    assert resp_appr.status_code == 403

    # 4. Can view own salary slip
    resp_slip = client.get(f"/payroll/slip/{rec1_id}")
    assert resp_slip.status_code == 200
    assert b"SAMPLE" in resp_slip.data
    assert b"Sample Salary Slip Preview" in resp_slip.data
    assert b"Ramesh Poojary" in resp_slip.data

    # 5. Strictly CANNOT view another employee's salary slip -> 403 Forbidden
    resp_forbidden = client.get(f"/payroll/slip/{rec_other_id}")
    assert resp_forbidden.status_code == 403
