from datetime import date, timedelta
from app.database import db
from app.models.employee import Employee
from app.models.attendance import DailyAttendance
from app.models.harvest import HarvestRecord
from app.models.farm import EstateBlock
from app.models.inventory import InventoryItem
from app.models.payroll import PayrollRecord

def test_reports_page_load(client, auth_client, app):
    """Tests that reports page renders successfully with summary cards and charts."""
    auth_client.login_manager()
    resp = client.get("/reports/")
    assert resp.status_code == 200
    assert b"Page 19: Reports" in resp.data
    assert b"Daily Attendance Trends" in resp.data
    assert b"Harvest Yield by Block" in resp.data
    assert b"Inventory Levels vs Minimum Threshold" in resp.data


def test_reports_date_filters(client, auth_client, app):
    """Verifies that preset and custom date filters operate cleanly without errors."""
    auth_client.login_manager()
    presets = ["today", "7days", "month", "30days", "ytd"]
    for p in presets:
        resp = client.get(f"/reports/?preset={p}")
        assert resp.status_code == 200

    # Custom date filter
    resp_custom = client.get("/reports/?start_date=2026-10-01&end_date=2026-10-15")
    assert resp_custom.status_code == 200


def test_reports_csv_exports_and_rbac(client, auth_client, app):
    """Tests CSV generation for attendance, harvest, inventory, and checks payroll export RBAC."""
    with app.app_context():
        emp = Employee.query.filter_by(employee_code="EMP001").first()
        # Seed attendance
        db.session.add(DailyAttendance(
            employee_id=emp.id,
            date=date.today(),
            shift="Morning Shift",
            status="Present",
            approved_by="Manager"
        ))

        # Seed harvest
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Test Block", area=5.0, unit="Hectares", variety="Arabica", location="Ridge", planting_date=date.today())
            db.session.add(block)
            db.session.commit()

        db.session.add(HarvestRecord(
            block_id=block.id,
            date=date.today(),
            planned_quantity=100.0,
            actual_quantity=125.5,
            team_id="Team Alpha",
            processing_status="Raw Cherry",
            notes="Morning pick"
        ))

        # Seed inventory
        db.session.add(InventoryItem(
            name="Copper Oxychloride Fungicide",
            category="Crop Protection",
            unit="kg",
            current_balance=25.0,
            reorder_level=50.0,
        ))

        # Seed payroll
        db.session.add(PayrollRecord(
            employee_id=emp.id,
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            period_label="Current Cycle",
            daily_wage=650.0,
            payable_days=10.0,
            gross_pay=6500.0,
            net_pay=6500.0,
            status="Approved"
        ))
        db.session.commit()

    # 1. Manager can export attendance, harvest, inventory, and payroll CSV
    auth_client.login_manager()
    
    resp_att = client.get("/reports/export/csv?type=attendance")
    assert resp_att.status_code == 200
    assert resp_att.mimetype == "text/csv"
    assert b"Employee Code" in resp_att.data

    resp_harv = client.get("/reports/export/csv?type=harvest")
    assert resp_harv.status_code == 200
    assert resp_harv.mimetype == "text/csv"
    assert b"Team Alpha" in resp_harv.data
    assert b"125.5" in resp_harv.data

    resp_inv = client.get("/reports/export/csv?type=inventory")
    assert resp_inv.status_code == 200
    assert resp_inv.mimetype == "text/csv"
    assert b"Copper Oxychloride Fungicide" in resp_inv.data

    resp_pay = client.get("/reports/export/csv?type=payroll")
    assert resp_pay.status_code == 200
    assert resp_pay.mimetype == "text/csv"
    assert b"Slip ID" in resp_pay.data
    assert b"Current Cycle" in resp_pay.data

    # 2. Worker (Employee) cannot export payroll CSV -> 403 Forbidden
    auth_client.logout()
    auth_client.login_employee()
    resp_pay_denied = client.get("/reports/export/csv?type=payroll")
    assert resp_pay_denied.status_code == 403
