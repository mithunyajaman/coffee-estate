import uuid
import json
import math
from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.exc import IntegrityError
from app.database import db
from app.models.employee import Employee
from app.models.attendance import DailyAttendance, AttendanceEvent, FaceEnrollment
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

attendance_bp = Blueprint("attendance", __name__)

# ==============================================================================
# PAGE 13: Manual & Offline Attendance Roster
# ==============================================================================

@attendance_bp.route("/attendance/manual", methods=["GET"])
@login_required
def manual_attendance():
    """Page 13: Manual and Offline Attendance Entry with conflict review panel."""
    current_user = get_current_user()
    selected_date_str = request.args.get("date") or str(date.today())
    selected_shift = request.args.get("shift") or "Morning Shift"

    try:
        att_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
    except ValueError:
        att_date = date.today()
        selected_date_str = str(att_date)

    employees = Employee.query.filter_by(status="Active").order_by(Employee.employee_code.asc()).all()

    # Load existing attendance for this date & shift
    existing_records = DailyAttendance.query.filter_by(date=att_date, shift=selected_shift).all()
    records_by_emp_id = {r.employee_id: r for r in existing_records}

    # Identify any conflicts flagged by offline sync
    conflict_records = DailyAttendance.query.filter_by(date=att_date, shift=selected_shift, has_conflict=True).all()

    # Tally
    total_staff = len(employees)
    present_count = sum(1 for r in existing_records if r.status == "Present")
    halfday_count = sum(1 for r in existing_records if r.status == "Half-day")
    leave_count = sum(1 for r in existing_records if r.status in ("On Leave", "Absent"))

    return render_template(
        "attendance_manual.html",
        employees=employees,
        records_by_emp_id=records_by_emp_id,
        conflict_records=conflict_records,
        selected_date=selected_date_str,
        selected_shift=selected_shift,
        total_staff=total_staff,
        present_count=present_count,
        halfday_count=halfday_count,
        leave_count=leave_count,
        current_user=current_user,
    )


@attendance_bp.route("/attendance/manual/bulk-save", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def bulk_save_attendance():
    """Bulk save manual attendance for a date and shift."""
    current_user = get_current_user()
    date_str = request.form.get("date") or str(date.today())
    shift = request.form.get("shift") or "Morning Shift"

    try:
        att_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        att_date = date.today()

    employees = Employee.query.filter_by(status="Active").all()
    saved_count = 0

    for emp in employees:
        status_key = f"status_{emp.id}"
        notes_key = f"reason_{emp.id}"
        new_status = request.form.get(status_key)
        reason = request.form.get(notes_key) or None

        if not new_status:
            continue

        record = DailyAttendance.query.filter_by(
            employee_id=emp.id,
            date=att_date,
            shift=shift
        ).first()

        if record:
            if record.status != new_status or record.has_conflict:
                record.status = new_status
                record.approved_by = current_user.username
                record.correction_reason = reason
                record.has_conflict = False
                saved_count += 1
        else:
            record = DailyAttendance(
                employee_id=emp.id,
                date=att_date,
                shift=shift,
                status=new_status,
                approved_by=current_user.username,
                correction_reason=reason,
                has_conflict=False,
            )
            db.session.add(record)
            saved_count += 1

    db.session.commit()

    log_audit(
        action="MANUAL_ATTENDANCE_BULK_SAVE",
        entity_type="DailyAttendance",
        entity_id=f"{att_date}_{shift}",
        outcome="SUCCESS",
        details=f"Saved attendance for {saved_count} workers on {att_date} ({shift})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Successfully saved attendance for {saved_count} employees on {att_date} ({shift}).", "success")
    return redirect(url_for("attendance.manual_attendance", date=date_str, shift=shift))


@attendance_bp.route("/api/attendance/sync", methods=["POST"])
@login_required
def sync_offline_attendance():
    """Idempotent sync endpoint for offline IndexedDB queue."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    events = data.get("events", [])

    if not isinstance(events, list) or len(events) == 0:
        return jsonify({"synced": 0, "conflicts": 0, "message": "No events supplied"}), 200

    synced_count = 0
    conflict_count = 0
    device_id = data.get("device_id", "Unknown Device")

    for ev in events:
        event_uuid = ev.get("event_uuid") or str(uuid.uuid4())
        emp_id = ev.get("employee_id")
        date_str = ev.get("date") or str(date.today())
        shift = ev.get("shift", "Morning Shift")
        status = ev.get("status", "Present")
        ev_type = ev.get("event_type", "Check-in")

        # Idempotency check: Ignore duplicate event UUID
        existing_event = AttendanceEvent.query.filter_by(event_uuid=event_uuid).first()
        if existing_event:
            continue

        try:
            ev_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            ev_date = date.today()

        emp = db.session.get(Employee, emp_id)
        if not emp:
            continue

        # Check for conflict against existing daily record
        daily = DailyAttendance.query.filter_by(
            employee_id=emp.id,
            date=ev_date,
            shift=shift
        ).first()

        is_conflict = False
        if daily and daily.status != status:
            # Conflict detected: Do not overwrite silently; flag for manager resolution!
            daily.has_conflict = True
            daily.correction_reason = f"Conflict between online status '{daily.status}' and offline queue '{status}' (Device: {device_id})"
            is_conflict = True
            conflict_count += 1
        elif not daily:
            daily = DailyAttendance(
                employee_id=emp.id,
                date=ev_date,
                shift=shift,
                status=status,
                approved_by="Offline Sync",
                has_conflict=False,
            )
            db.session.add(daily)

        # Store raw immutable event
        att_event = AttendanceEvent(
            event_uuid=event_uuid,
            employee_id=emp.id,
            event_type=ev_type,
            method="Offline_Sync",
            confidence=1.0,
            device_id=device_id,
            sync_status="Conflict" if is_conflict else "Synced",
            created_by=current_user.username,
        )
        db.session.add(att_event)
        synced_count += 1

    db.session.commit()

    log_audit(
        action="OFFLINE_ATTENDANCE_SYNC",
        entity_type="AttendanceEvent",
        entity_id=device_id,
        outcome="SUCCESS",
        details=f"Synced {synced_count} offline attendance records ({conflict_count} conflicts flagged).",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return jsonify({
        "success": True,
        "synced": synced_count,
        "conflicts": conflict_count,
        "message": f"Successfully synced {synced_count} records ({conflict_count} conflicts flagged for manager review)."
    })


# ==============================================================================
# PAGE 11: Face Registration & Biometric Consent Workflow
# ==============================================================================

@attendance_bp.route("/attendance/face-register", methods=["GET"])
@login_required
def face_registration_page():
    """Page 11: Face Registration with explicit consent, vector enrollment, and revoke workflow."""
    current_user = get_current_user()
    employees = Employee.query.filter_by(status="Active").order_by(Employee.employee_code.asc()).all()

    # Pre-select employee if current user is linked to one
    my_emp = None
    if current_user.employee_code:
        my_emp = Employee.query.filter_by(employee_code=current_user.employee_code).first()

    enrollments = FaceEnrollment.query.all()
    enrollment_by_emp_id = {e.employee_id: e for e in enrollments}

    return render_template(
        "face_register.html",
        employees=employees,
        my_emp=my_emp,
        enrollment_by_emp_id=enrollment_by_emp_id,
        current_user=current_user,
    )


@attendance_bp.route("/api/attendance/face-enroll", methods=["POST"])
@login_required
def face_enroll():
    """Store explicit biometric consent and mathematical feature vector (no raw images)."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    consent = bool(data.get("consent"))
    embedding = data.get("embedding") # Array of floats representing landmarks/features
    threshold = float(data.get("threshold", 0.75))

    if not consent:
        return jsonify({"error": "Explicit biometric consent is required under privacy rules."}), 400

    if not employee_id or not embedding or not isinstance(embedding, list):
        return jsonify({"error": "Employee ID and facial mathematical template are required."}), 400

    emp = db.session.get(Employee, employee_id)
    if not emp:
        return jsonify({"error": "Employee not found."}), 404

    # If regular employee, only allow self-enrollment
    if current_user.is_employee:
        my_emp = Employee.query.filter_by(employee_code=current_user.employee_code).first()
        if not my_emp or my_emp.id != emp.id:
            return jsonify({"error": "You may only register biometric data for your own account."}), 403

    existing = FaceEnrollment.query.filter_by(employee_id=emp.id).first()
    if existing:
        existing.consent_status = True
        existing.consent_timestamp = datetime.now(timezone.utc)
        existing.protected_template = json.dumps(embedding)
        existing.enrollment_status = "Enrolled"
        existing.confidence_threshold = threshold
    else:
        existing = FaceEnrollment(
            employee_id=emp.id,
            consent_status=True,
            consent_timestamp=datetime.now(timezone.utc),
            protected_template=json.dumps(embedding),
            enrollment_status="Enrolled",
            confidence_threshold=threshold,
        )
        db.session.add(existing)

    db.session.commit()

    log_audit(
        action="FACE_BIOMETRIC_ENROLLED",
        entity_type="FaceEnrollment",
        entity_id=str(emp.id),
        outcome="SUCCESS",
        details=f"Biometric template enrolled for {emp.employee_code} ({emp.name}) with explicit consent.",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return jsonify({
        "success": True,
        "message": f"Biometric verification template registered for {emp.name} ({emp.employee_code}). Raw images were safely discarded.",
        "employee_code": emp.employee_code,
    })


@attendance_bp.route("/api/attendance/face-revoke", methods=["POST"])
@login_required
def face_revoke():
    """Revoke and delete biometric enrollment data."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")

    emp = db.session.get(Employee, employee_id)
    if not emp:
        return jsonify({"error": "Employee not found."}), 404

    # If regular employee, only allow self-revocation
    if current_user.is_employee:
        my_emp = Employee.query.filter_by(employee_code=current_user.employee_code).first()
        if not my_emp or my_emp.id != emp.id:
            return jsonify({"error": "Unauthorized"}), 403

    enrollment = FaceEnrollment.query.filter_by(employee_id=emp.id).first()
    if enrollment:
        db.session.delete(enrollment)
        db.session.commit()

        log_audit(
            action="FACE_BIOMETRIC_REVOKED",
            entity_type="FaceEnrollment",
            entity_id=str(emp.id),
            outcome="SUCCESS",
            details=f"Biometric template permanently purged for {emp.employee_code} ({emp.name}).",
            actor_id=current_user.id,
            actor_username=current_user.username,
        )

    return jsonify({
        "success": True,
        "message": f"Biometric data permanently revoked and deleted for {emp.name}.",
    })


# ==============================================================================
# PAGE 12: Face Attendance (Verification & Check-in / Check-out)
# ==============================================================================

@attendance_bp.route("/attendance/face-checkin", methods=["GET"])
@login_required
def face_attendance_page():
    """Page 12: Face Attendance Verification with camera guide and manual fallback."""
    current_user = get_current_user()
    today_records = DailyAttendance.query.filter_by(date=date.today()).all()
    today_events = (
        AttendanceEvent.query.filter_by(method="Face")
        .order_by(AttendanceEvent.timestamp.desc())
        .limit(8)
        .all()
    )

    enrolled_count = FaceEnrollment.query.filter_by(enrollment_status="Enrolled").count()

    return render_template(
        "face_attendance.html",
        today_events=today_events,
        enrolled_count=enrolled_count,
        current_user=current_user,
    )


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


@attendance_bp.route("/api/attendance/face-verify", methods=["POST"])
@login_required
def face_verify():
    """Match captured frame template against enrolled biometric profiles."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    sample_vector = data.get("vector") # 128D mathematical vector
    event_type = data.get("event_type", "Check-in") # Check-in or Check-out

    if not sample_vector or not isinstance(sample_vector, list):
        return jsonify({"matched": False, "error": "No valid facial template extracted from frame."}), 400

    # Retrieve all active enrolled biometric profiles
    enrollments = FaceEnrollment.query.filter_by(enrollment_status="Enrolled").all()
    if not enrollments:
        return jsonify({
            "matched": False,
            "error": "No enrolled biometric profiles found in database. Please enroll first."
        }), 404

    best_match = None
    best_similarity = 0.0

    for enr in enrollments:
        try:
            stored_vector = json.loads(enr.protected_template)
            sim = cosine_similarity(sample_vector, stored_vector)
            if sim > best_similarity:
                best_similarity = sim
                best_match = enr
        except Exception:
            continue

    threshold = best_match.confidence_threshold if best_match else 0.75

    # STRICT THRESHOLD ENFORCEMENT & MANUAL FALLBACK
    if not best_match or best_similarity < threshold:
        return jsonify({
            "matched": False,
            "confidence": round(best_similarity, 3),
            "threshold": threshold,
            "error": f"Low-confidence match ({round(best_similarity * 100, 1)}% - below required threshold of {int(threshold * 100)}%). Verification rejected to prevent false acceptance.",
            "fallback_url": url_for("attendance.manual_attendance"),
        }), 422

    emp = best_match.employee

    # Duplicate Prevention Check: Disallow duplicate check-ins within 5 minutes
    five_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_dup = AttendanceEvent.query.filter(
        AttendanceEvent.employee_id == emp.id,
        AttendanceEvent.event_type == event_type,
        AttendanceEvent.timestamp >= five_mins_ago
    ).first()

    if recent_dup:
        return jsonify({
            "matched": True,
            "confidence": round(best_similarity, 3),
            "employee_name": emp.name,
            "employee_code": emp.employee_code,
            "warning": f"Duplicate event: {emp.name} already recorded a {event_type} at {recent_dup.timestamp.strftime('%H:%M:%S UTC')}."
        }), 409

    # Record valid biometric event
    att_event = AttendanceEvent(
        event_uuid=str(uuid.uuid4()),
        employee_id=emp.id,
        event_type=event_type,
        method="Face",
        confidence=round(best_similarity, 3),
        device_id="Biometric Terminal",
        sync_status="Synced",
        created_by=current_user.username,
    )
    db.session.add(att_event)

    # Upsert daily attendance record
    today = date.today()
    daily = DailyAttendance.query.filter_by(
        employee_id=emp.id,
        date=today,
        shift="Morning Shift"
    ).first()

    if not daily:
        daily = DailyAttendance(
            employee_id=emp.id,
            date=today,
            shift="Morning Shift",
            status="Present",
            approved_by="Face Verification AI",
            has_conflict=False,
        )
        db.session.add(daily)

    db.session.commit()

    log_audit(
        action="FACE_ATTENDANCE_VERIFIED",
        entity_type="AttendanceEvent",
        entity_id=str(emp.id),
        outcome="SUCCESS",
        details=f"Verified {emp.employee_code} ({emp.name}) with {round(best_similarity * 100, 1)}% confidence for {event_type}.",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return jsonify({
        "matched": True,
        "confidence": round(best_similarity, 3),
        "employee_name": emp.name,
        "employee_code": emp.employee_code,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "message": f"Welcome, {emp.name}! {event_type} recorded successfully ({round(best_similarity * 100, 1)}% match).",
    })
