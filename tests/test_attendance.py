import json
import math
from datetime import date
from app.database import db
from app.models.employee import Employee
from app.models.attendance import DailyAttendance, AttendanceEvent, FaceEnrollment
from app.models.audit import AuditLog

# ==========================================
# 1. Manual Attendance Tests (Page 13)
# ==========================================

def test_view_manual_attendance(client, auth_client):
    """Authenticated users can view attendance muster roll."""
    auth_client.login_manager()
    resp = client.get("/attendance/manual")
    assert resp.status_code == 200
    assert b"Daily Attendance Roster" in resp.data

def test_bulk_save_manual_attendance(client, auth_client):
    """Manager can bulk-save daily attendance for workers."""
    auth_client.login_manager()
    emp = Employee.query.first() or Employee(employee_code="EMP_TEST", name="Test Worker", contact="111", job_role="Worker")
    db.session.add(emp)
    db.session.commit()

    resp = client.post("/attendance/manual/bulk-save", data={
        "date": "2026-10-26",
        "shift": "Morning Shift",
        f"status_{emp.id}": "Present",
        f"reason_{emp.id}": "Regular morning shift"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Successfully saved attendance" in resp.data

    record = DailyAttendance.query.filter_by(employee_id=emp.id, date=date(2026, 10, 26), shift="Morning Shift").first()
    assert record is not None
    assert record.status == "Present"

    # Audit log recorded
    audit = AuditLog.query.filter_by(action="MANUAL_ATTENDANCE_BULK_SAVE").first()
    assert audit is not None


# ==========================================
# 2. Offline Sync & Conflict Detection
# ==========================================

def test_offline_sync_idempotency(client, auth_client):
    """Idempotent sync: duplicate event UUIDs do not create duplicate records."""
    auth_client.login_manager()
    emp = Employee.query.first()
    assert emp is not None

    payload = {
        "device_id": "Field Tablet #4",
        "events": [
            {
                "event_uuid": "offline-uuid-101",
                "employee_id": emp.id,
                "date": "2026-10-26",
                "shift": "General Shift",
                "status": "Present",
                "event_type": "Check-in"
            }
        ]
    }

    # First sync call
    resp1 = client.post("/api/attendance/sync", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["synced"] == 1

    # Second sync call with exact same UUID (should be ignored idempotently)
    resp2 = client.post("/api/attendance/sync", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["synced"] == 0

    events_count = AttendanceEvent.query.filter_by(event_uuid="offline-uuid-101").count()
    assert events_count == 1

def test_offline_sync_conflict_flagging(client, auth_client):
    """Conflict detection: Offline record conflicting with online entry is flagged for manager review."""
    auth_client.login_manager()
    emp = Employee.query.first()

    # Pre-existing online record marks employee Present
    existing = DailyAttendance(
        employee_id=emp.id,
        date=date(2026, 10, 27),
        shift="Morning Shift",
        status="Present",
        approved_by="Manager",
    )
    db.session.add(existing)
    db.session.commit()

    # Offline queue from field supervisor says employee was Absent
    payload = {
        "device_id": "Field Tablet #2",
        "events": [
            {
                "event_uuid": "offline-conflict-uuid-202",
                "employee_id": emp.id,
                "date": "2026-10-27",
                "shift": "Morning Shift",
                "status": "Absent",
                "event_type": "Check-in"
            }
        ]
    }

    resp = client.post("/api/attendance/sync", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["conflicts"] == 1

    db.session.refresh(existing)
    assert existing.has_conflict is True
    assert "Conflict between online status 'Present' and offline queue 'Absent'" in existing.correction_reason


# ==========================================
# 3. Biometric Consent & Face Registration
# ==========================================

def test_face_enrollment_requires_consent(client, auth_client):
    """Enrolling without explicit consent is rejected under privacy rules."""
    auth_client.login_manager()
    emp = Employee.query.first()

    resp = client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "consent": False,
        "embedding": [0.1] * 128
    })
    assert resp.status_code == 400
    assert "Explicit biometric consent is required" in resp.get_json()["error"]

def test_face_enrollment_success_and_revocation(client, auth_client):
    """Enroll mathematical vector and allow permanent deletion."""
    auth_client.login_manager()
    emp = Employee.query.first()
    vector = [0.25] * 128

    resp_enroll = client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "consent": True,
        "embedding": vector,
        "threshold": 0.75
    })
    assert resp_enroll.status_code == 200
    assert "registered" in resp_enroll.get_json()["message"]

    enr = FaceEnrollment.query.filter_by(employee_id=emp.id).first()
    assert enr is not None
    assert enr.consent_status is True
    assert enr.enrollment_status == "Enrolled"

    # Revoke enrollment
    resp_revoke = client.post("/api/attendance/face-revoke", json={
        "employee_id": emp.id
    })
    assert resp_revoke.status_code == 200
    assert "permanently revoked" in resp_revoke.get_json()["message"]

    enr_after = FaceEnrollment.query.filter_by(employee_id=emp.id).first()
    assert enr_after is None


# ==========================================
# 4. Face Attendance Verification & Thresholds
# ==========================================

def test_face_verify_success_and_duplicate_check(client, auth_client):
    """Verified match records check-in and rejects duplicate clock-ins within 5 minutes."""
    auth_client.login_manager()
    emp = Employee.query.first()
    target_vector = [0.5] * 128

    # Enroll employee
    client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "consent": True,
        "embedding": target_vector,
        "threshold": 0.75
    })

    # First clock-in: Identical vector (100% match)
    resp1 = client.post("/api/attendance/face-verify", json={
        "vector": target_vector,
        "event_type": "Check-in"
    })
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["matched"] is True
    assert data1["confidence"] >= 0.75
    assert data1["employee_code"] == emp.employee_code

    # Second immediate clock-in: Duplicate prevention triggers 409 Conflict
    resp2 = client.post("/api/attendance/face-verify", json={
        "vector": target_vector,
        "event_type": "Check-in"
    })
    assert resp2.status_code == 409
    assert "Duplicate event" in resp2.get_json()["warning"]

def test_face_verify_low_confidence_rejected_with_fallback(client, auth_client):
    """Uncertain matches below confidence threshold are rejected with manual fallback."""
    auth_client.login_manager()
    emp = Employee.query.first()

    # Enroll vector of all 1.0s
    client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "consent": True,
        "embedding": [1.0] * 128,
        "threshold": 0.75
    })

    # Test with orthogonal / mismatched vector (e.g. all 0.0s or random low similarity)
    mismatched = [0.0] * 128
    resp = client.post("/api/attendance/face-verify", json={
        "vector": mismatched,
        "event_type": "Check-in"
    })
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["matched"] is False
    assert data["coffee_status"] == "Red Coffee"
    assert data["status"] == "Unverified"
    assert "below required threshold" in data["error"]
    assert "fallback_url" in data


def test_face_verify_red_coffee_on_targeted_mismatch(client, auth_client):
    """When a specific Roll No is targeted but a different/mismatched face is scanned, it returns Red Coffee."""
    auth_client.login_manager()
    emp = Employee.query.first()

    # Enroll employee with vector of all 0.5s
    client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "roll_no": emp.employee_code,
        "consent": True,
        "embedding": [0.5] * 128,
        "threshold": 0.75
    })

    # Verify with completely mismatched vector
    mismatch_vector = [0.0] * 128
    resp = client.post("/api/attendance/face-verify", json={
        "vector": mismatch_vector,
        "employee_id": emp.id,
        "event_type": "Check-in"
    })
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["matched"] is False
    assert data["coffee_status"] == "Red Coffee"
    assert data["status"] == "Unverified"
    assert data["employee_name"] == emp.name
    assert "Biometric mismatch" in data["error"]


def test_employee_cannot_drop_attendance(client, auth_client):
    """Field workers receive 403 Forbidden when attempting to view or drop manual attendance."""
    auth_client.login_employee()
    
    # Attempt to view manual roster
    resp_view = client.get("/attendance/manual")
    assert resp_view.status_code == 403

    # Attempt to bulk-save attendance
    resp_save = client.post("/attendance/manual/bulk-save", data={"date": "2026-10-26", "shift": "Morning Shift"})
    assert resp_save.status_code == 403


def test_employee_blocked_from_all_biometric_actions(client, auth_client):
    """Only Estate Manager and Admin can access biometric terminals and enroll or take attendance."""
    auth_client.login_employee()

    # 1. Blocked from biometric attendance kiosk page
    resp_checkin_page = client.get("/attendance/face-checkin")
    assert resp_checkin_page.status_code == 403

    # 2. Blocked from biometric verification API
    resp_verify_api = client.post("/api/attendance/face-verify", json={
        "vector": [0.5] * 128,
        "event_type": "Check-in"
    })
    assert resp_verify_api.status_code == 403

    # 3. Blocked from biometric registration page
    resp_register_page = client.get("/attendance/face-register")
    assert resp_register_page.status_code == 403

    # 4. Blocked from biometric enrollment API
    resp_enroll_api = client.post("/api/attendance/face-enroll", json={
        "roll_no": "EMP001",
        "consent": True,
        "embedding": [0.5] * 128
    })
    assert resp_enroll_api.status_code == 403

    # 5. Blocked from biometric revocation API
    resp_revoke_api = client.post("/api/attendance/face-revoke", json={
        "roll_no": "EMP001"
    })
    assert resp_revoke_api.status_code == 403

    # 6. Blocked from offline attendance sync API
    resp_sync_api = client.post("/api/attendance/sync", json={"events": []})
    assert resp_sync_api.status_code == 403


def test_manager_enrollment_and_verification_with_roll_no(client, auth_client):
    """Estate Manager can enroll and verify employee attendance directly using Roll No."""
    auth_client.login_manager()
    emp = Employee.query.filter_by(employee_code="EMP002").first() or Employee.query.first()
    assert emp is not None

    test_vector = [0.65] * 128

    # 1. Enroll using Roll No
    resp_enroll = client.post("/api/attendance/face-enroll", json={
        "roll_no": emp.employee_code,
        "consent": True,
        "embedding": test_vector,
        "threshold": 0.75
    })
    assert resp_enroll.status_code == 200
    enroll_data = resp_enroll.get_json()
    assert enroll_data["success"] is True
    assert enroll_data["roll_no"] == emp.employee_code

    # 2. Verify attendance using Roll No
    resp_verify = client.post("/api/attendance/face-verify", json={
        "vector": test_vector,
        "roll_no": emp.employee_code,
        "event_type": "Check-in",
        "shift": "Morning Shift"
    })
    assert resp_verify.status_code == 200
    verify_data = resp_verify.get_json()
    assert verify_data["matched"] is True
    assert verify_data["roll_no"] == emp.employee_code
    assert verify_data["coffee_status"] == "Green Coffee"
    assert verify_data["status"] == "Present"

    # 3. Confirm daily attendance marked Present
    daily = DailyAttendance.query.filter_by(employee_id=emp.id, date=date.today()).first()
    assert daily is not None
    assert daily.status == "Present"


def test_green_coffee_targeted_face_verification(client, auth_client):
    """Admin/Manager can verify a specific employee's face and mark Green Coffee (Present)."""
    auth_client.login_manager()
    emp = Employee.query.first()
    target_vector = [0.8] * 128

    # Enroll employee
    client.post("/api/attendance/face-enroll", json={
        "employee_id": emp.id,
        "consent": True,
        "embedding": target_vector,
        "threshold": 0.75
    })

    # Targeted verification
    resp = client.post("/api/attendance/face-verify", json={
        "vector": target_vector,
        "employee_id": emp.id,
        "event_type": "Check-in"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["matched"] is True
    assert data["coffee_status"] == "Green Coffee"
    assert data["status"] == "Present"

    # Check daily attendance was updated as Present
    daily = DailyAttendance.query.filter_by(employee_id=emp.id, date=date.today()).first()
    assert daily is not None
    assert daily.status == "Present"


# ==========================================
# 5. Add Employee with Face & Roll No Tests
# ==========================================

def test_manager_can_add_employee_with_face_and_new_roll_no(client, auth_client):
    """Estate Manager can add a new employee, assign a new Roll No, enroll face, and mark attendance in 1 step."""
    auth_client.login_manager()
    new_vector = [0.42] * 128
    
    resp = client.post("/attendance/add-employee-with-face", json={
        "roll_no": "EMP099",
        "name": "Kavitha Gowda",
        "job_role": "Coffee Picker",
        "wage_rate": "550.0",
        "contact": "+91-9988776655",
        "consent": True,
        "mark_attendance_now": True,
        "embedding": new_vector,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["employee"]["roll_no"] == "EMP099"
    assert data["employee"]["name"] == "Kavitha Gowda"

    # Verify employee exists in DB
    created_emp = Employee.query.filter_by(employee_code="EMP099").first()
    assert created_emp is not None
    assert created_emp.name == "Kavitha Gowda"
    assert created_emp.job_role == "Coffee Picker"

    # Verify face enrollment exists
    enrollment = FaceEnrollment.query.filter_by(employee_id=created_emp.id).first()
    assert enrollment is not None
    assert enrollment.enrollment_status == "Enrolled"
    assert enrollment.consent_status is True

    # Verify today's attendance is marked Present (Green Coffee)
    daily = DailyAttendance.query.filter_by(employee_id=created_emp.id, date=date.today()).first()
    assert daily is not None
    assert daily.status == "Present"
    
    event = AttendanceEvent.query.filter_by(employee_id=created_emp.id).first()
    assert event is not None
    assert event.method == "Face"
    assert event.event_type == "Check-in"


def test_worker_forbidden_from_adding_employee_with_face(client, auth_client):
    """Field worker (regular employee) is strictly forbidden (403) from adding employees with face."""
    auth_client.login_employee()
    resp = client.post("/attendance/add-employee-with-face", json={
        "roll_no": "EMP100",
        "name": "Unauthorized Add",
        "consent": True
    })
    assert resp.status_code == 403


def test_add_employee_duplicate_roll_no_blocked(client, auth_client):
    """Adding an employee with an existing Roll No is rejected."""
    auth_client.login_manager()
    existing = Employee.query.first()
    assert existing is not None

    resp = client.post("/attendance/add-employee-with-face", json={
        "roll_no": existing.employee_code,
        "name": "Duplicate Person",
        "consent": True
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "already assigned" in data["error"]
