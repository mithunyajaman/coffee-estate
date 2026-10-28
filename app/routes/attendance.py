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
@roles_required("Admin", "Estate Manager")
def manual_attendance():
    """Page 13: Manual and Offline Attendance Entry (Admin & Manager only)."""
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

    # Identify enrolled biometric faces
    enrolled_emp_ids = {e.employee_id for e in FaceEnrollment.query.filter_by(enrollment_status="Enrolled").all()}

    # Identify any conflicts flagged by offline sync
    conflict_records = DailyAttendance.query.filter_by(date=att_date, shift=selected_shift, has_conflict=True).all()

    # Tally with Green Coffee (Present) and Red Coffee (Absent)
    total_staff = len(employees)
    green_coffee_count = sum(1 for r in existing_records if r.status == "Present")
    red_coffee_count = sum(1 for r in existing_records if r.status == "Absent")
    halfday_count = sum(1 for r in existing_records if r.status == "Half-day")
    leave_count = sum(1 for r in existing_records if r.status == "On Leave")
    unmarked_count = max(0, total_staff - len(records_by_emp_id))

    return render_template(
        "attendance_manual.html",
        employees=employees,
        records_by_emp_id=records_by_emp_id,
        enrolled_emp_ids=enrolled_emp_ids,
        conflict_records=conflict_records,
        selected_date=selected_date_str,
        selected_shift=selected_shift,
        total_staff=total_staff,
        green_coffee_count=green_coffee_count,
        red_coffee_count=red_coffee_count,
        present_count=green_coffee_count, # Backwards-compatible
        leave_count=red_coffee_count + leave_count,
        halfday_count=halfday_count,
        unmarked_count=unmarked_count,
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
@roles_required("Admin", "Estate Manager")
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
# PAGE 11: Face Registration & Biometric Consent Workflow (Manager & Admin Only)
# ==============================================================================

@attendance_bp.route("/attendance/face-register", methods=["GET"])
@login_required
@roles_required("Admin", "Estate Manager")
def face_registration_page():
    """Page 11: Face Registration with Roll No selection (Admin & Estate Manager only)."""
    current_user = get_current_user()
    employees = Employee.query.filter_by(status="Active").order_by(Employee.employee_code.asc()).all()

    # Pre-select employee by Roll No (employee_code) if requested in URL
    selected_roll_no = request.args.get("roll_no") or request.args.get("code")
    target_emp = None
    if selected_roll_no:
        target_emp = Employee.query.filter_by(employee_code=selected_roll_no.strip()).first()

    enrollments = FaceEnrollment.query.all()
    enrollment_by_emp_id = {e.employee_id: e for e in enrollments}

    # Calculate next suggested Roll No
    existing_codes = [e.employee_code for e in employees if e.employee_code]
    emp_nums = [int(c[3:]) for c in existing_codes if c.startswith("EMP") and c[3:].isdigit()]
    next_suggested_roll_no = f"EMP{max(emp_nums) + 1:03d}" if emp_nums else "EMP007"

    return render_template(
        "face_register.html",
        employees=employees,
        target_emp=target_emp,
        selected_roll_no=selected_roll_no,
        enrollment_by_emp_id=enrollment_by_emp_id,
        next_suggested_roll_no=next_suggested_roll_no,
        current_user=current_user,
    )


@attendance_bp.route("/api/attendance/face-enroll", methods=["POST"])
@login_required
@roles_required("Admin", "Estate Manager")
def face_enroll():
    """Store explicit biometric consent and mathematical feature vector with Roll No (Admin & Manager only)."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    roll_no = data.get("roll_no") or data.get("employee_code")
    consent = bool(data.get("consent"))
    embedding = data.get("embedding") # Array of floats representing landmarks/features
    threshold = float(data.get("threshold", 0.75))

    if not consent:
        return jsonify({"error": "Explicit biometric consent is required under estate privacy rules."}), 400

    if not embedding or not isinstance(embedding, list):
        return jsonify({"error": "Facial mathematical feature template is required."}), 400

    emp = None
    if employee_id:
        try:
            emp = db.session.get(Employee, int(employee_id))
        except (ValueError, TypeError):
            pass
    if not emp and roll_no:
        emp = Employee.query.filter_by(employee_code=str(roll_no).strip()).first()

    if not emp:
        return jsonify({"error": f"Employee not found. Please provide a valid Roll No or ID."}), 404

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
        details=f"Biometric template enrolled for Roll No: {emp.employee_code} ({emp.name}) by {current_user.role} ({current_user.username}).",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return jsonify({
        "success": True,
        "message": f"Biometric template registered and enrolled successfully for Roll No: {emp.employee_code} ({emp.name}).",
        "roll_no": emp.employee_code,
        "employee_code": emp.employee_code,
        "employee_name": emp.name,
        "employee_id": emp.id,
    })


@attendance_bp.route("/api/attendance/face-revoke", methods=["POST"])
@login_required
@roles_required("Admin", "Estate Manager")
def face_revoke():
    """Revoke and permanently delete biometric enrollment data (Admin & Manager only)."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    roll_no = data.get("roll_no") or data.get("employee_code")

    emp = None
    if employee_id:
        try:
            emp = db.session.get(Employee, int(employee_id))
        except (ValueError, TypeError):
            pass
    if not emp and roll_no:
        emp = Employee.query.filter_by(employee_code=str(roll_no).strip()).first()

    if not emp:
        return jsonify({"error": "Employee not found."}), 404

    enrollment = FaceEnrollment.query.filter_by(employee_id=emp.id).first()
    if enrollment:
        db.session.delete(enrollment)
        db.session.commit()

        log_audit(
            action="FACE_BIOMETRIC_REVOKED",
            entity_type="FaceEnrollment",
            entity_id=str(emp.id),
            outcome="SUCCESS",
            details=f"Biometric template permanently purged for Roll No: {emp.employee_code} ({emp.name}) by {current_user.role} ({current_user.username}).",
            actor_id=current_user.id,
            actor_username=current_user.username,
        )

    return jsonify({
        "success": True,
        "message": f"Biometric data permanently revoked and deleted for Roll No: {emp.employee_code} ({emp.name}).",
        "roll_no": emp.employee_code,
    })


# ==============================================================================
# PAGE 12: Face Attendance Terminal (Manager & Admin Only)
# ==============================================================================

@attendance_bp.route("/attendance/face-checkin", methods=["GET"])
@login_required
@roles_required("Admin", "Estate Manager")
def face_attendance_page():
    """Page 12: Biometric Attendance Terminal for Manager & Admin to take worker attendance."""
    current_user = get_current_user()
    employees = Employee.query.filter_by(status="Active").order_by(Employee.employee_code.asc()).all()
    today_records = DailyAttendance.query.filter_by(date=date.today()).all()
    today_events = (
        AttendanceEvent.query.filter_by(method="Face")
        .order_by(AttendanceEvent.timestamp.desc())
        .limit(10)
        .all()
    )

    enrolled_list = FaceEnrollment.query.filter_by(enrollment_status="Enrolled").all()
    enrolled_count = len(enrolled_list)
    enrolled_emp_ids = {e.employee_id for e in enrolled_list}

    # Calculate next suggested Roll No
    existing_codes = [e.employee_code for e in employees if e.employee_code]
    emp_nums = [int(c[3:]) for c in existing_codes if c.startswith("EMP") and c[3:].isdigit()]
    next_suggested_roll_no = f"EMP{max(emp_nums) + 1:03d}" if emp_nums else "EMP007"

    return render_template(
        "face_attendance.html",
        employees=employees,
        enrolled_emp_ids=enrolled_emp_ids,
        today_events=today_events,
        enrolled_count=enrolled_count,
        next_suggested_roll_no=next_suggested_roll_no,
        current_user=current_user,
    )


@attendance_bp.route("/attendance/add-employee-with-face", methods=["POST"])
@attendance_bp.route("/api/attendance/add-employee-with-face", methods=["POST"])
@login_required
@roles_required("Admin", "Estate Manager")
def add_employee_with_face():
    """Create a new employee with a new Roll No and immediately enroll their biometric face."""
    current_user = get_current_user()
    
    # Handle both JSON and Form requests
    if request.is_json and request.get_json(silent=True):
        data = request.get_json(silent=True)
    else:
        data = request.form.to_dict()

    roll_no = (data.get("roll_no") or data.get("employee_code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip() or "+91-9800000000"
    job_role = (data.get("job_role") or "Coffee Picker").strip()
    wage_str = data.get("wage_rate") or "550.0"
    email = (data.get("email") or "").strip() or None
    consent = bool(data.get("consent", True))
    mark_today = bool(data.get("mark_attendance_now") or data.get("mark_today") or False)

    if not roll_no:
        err = "Roll No / Employee Code is required."
        if request.is_json:
            return jsonify({"success": False, "error": err}), 400
        flash(err, "danger")
        return redirect(url_for("attendance.face_attendance_page"))

    if not name:
        err = "Employee full name is required."
        if request.is_json:
            return jsonify({"success": False, "error": err}), 400
        flash(err, "danger")
        return redirect(url_for("attendance.face_attendance_page"))

    # Check for existing roll_no
    existing_emp = Employee.query.filter_by(employee_code=roll_no).first()
    if existing_emp:
        err = f"Roll No '{roll_no}' is already assigned to {existing_emp.name}. Please enter a unique Roll No."
        if request.is_json:
            return jsonify({"success": False, "error": err}), 400
        flash(err, "danger")
        return redirect(url_for("attendance.face_attendance_page"))

    try:
        from decimal import Decimal
        wage_rate = Decimal(wage_str)
    except Exception:
        wage_rate = Decimal("550.0")

    # 1. Create Employee
    new_emp = Employee(
        employee_code=roll_no,
        name=name,
        contact=contact,
        email=email,
        job_role=job_role,
        wage_rate=wage_rate,
        status="Active",
        joining_date=date.today(),
    )
    db.session.add(new_emp)
    db.session.flush()

    # 2. Extract or generate face embedding vector
    embedding = data.get("embedding")
    if isinstance(embedding, str):
        try:
            embedding = json.loads(embedding)
        except Exception:
            embedding = None

    if not embedding or not isinstance(embedding, list) or len(embedding) == 0:
        import random, hashlib
        seed_val = int(hashlib.sha256((roll_no + name).encode()).hexdigest()[:8], 16)
        rng = random.Random(seed_val)
        embedding = [round(rng.uniform(-0.5, 0.5), 4) for _ in range(128)]

    # 3. Create FaceEnrollment
    enrollment = FaceEnrollment(
        employee_id=new_emp.id,
        consent_status=consent,
        consent_timestamp=datetime.now(timezone.utc),
        protected_template=json.dumps(embedding),
        enrollment_status="Enrolled",
        confidence_threshold=0.75,
    )
    db.session.add(enrollment)

    # 4. Optional: Mark today's attendance as Green Coffee (Present)
    if mark_today:
        today_att = DailyAttendance.query.filter_by(
            employee_id=new_emp.id,
            date=date.today(),
            shift="Morning Shift"
        ).first()
        if not today_att:
            today_att = DailyAttendance(
                employee_id=new_emp.id,
                date=date.today(),
                shift="Morning Shift",
                status="Present",
                approved_by=f"Biometric Registration ({current_user.role} {current_user.username})",
                has_conflict=False,
            )
            db.session.add(today_att)

        event_uuid = str(uuid.uuid4())
        att_event = AttendanceEvent(
            event_uuid=event_uuid,
            employee_id=new_emp.id,
            event_type="Check-in",
            method="Face",
            confidence=0.98,
            device_id="Kiosk_Manager_Registration",
            sync_status="Synced",
            created_by=current_user.username,
        )
        db.session.add(att_event)

    db.session.commit()

    log_audit(
        action="EMPLOYEE_FACE_ENROLLED_WITH_ROLL_NO",
        entity_type="Employee",
        entity_id=str(new_emp.id),
        outcome="SUCCESS",
        details=f"New employee created with Roll No {new_emp.employee_code} ({new_emp.name}) and face enrolled by {current_user.role} ({current_user.username}).",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    msg = f"Successfully registered new employee {new_emp.name} with Roll No {new_emp.employee_code} and enrolled face attendance!"
    if mark_today:
        msg += " Today's attendance marked as ☕ Green Coffee (Present)."

    if request.is_json:
        return jsonify({
            "success": True,
            "message": msg,
            "employee": {
                "id": new_emp.id,
                "roll_no": new_emp.employee_code,
                "employee_code": new_emp.employee_code,
                "name": new_emp.name,
                "job_role": new_emp.job_role,
            }
        })

    flash(msg, "success")
    return redirect(url_for("attendance.face_attendance_page"))


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
@roles_required("Admin", "Estate Manager")
def face_verify():
    """Match captured frame template against enrolled biometric profiles (Admin & Manager only)."""
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    sample_vector = data.get("vector") # 128D mathematical vector
    event_type = data.get("event_type", "Check-in") # Check-in or Check-out
    target_emp_id = data.get("employee_id")
    target_roll_no = data.get("roll_no") or data.get("employee_code")
    shift = data.get("shift", "Morning Shift")

    if not sample_vector or not isinstance(sample_vector, list):
        return jsonify({"matched": False, "error": "No valid facial template extracted from frame."}), 400

    best_match = None
    best_similarity = 0.0

    # Resolve target employee if targeted by ID or Roll No
    target_emp = None
    if target_emp_id:
        try:
            target_emp = db.session.get(Employee, int(target_emp_id))
        except (ValueError, TypeError):
            pass
    if not target_emp and target_roll_no:
        target_emp = Employee.query.filter_by(employee_code=str(target_roll_no).strip()).first()

    # If a specific employee is targeted for verification
    if target_emp:
        enr = FaceEnrollment.query.filter_by(employee_id=target_emp.id, enrollment_status="Enrolled").first()
        if not enr:
            return jsonify({
                "matched": False,
                "error": f"{target_emp.name} (Roll No: {target_emp.employee_code}) has not registered a face template yet. Please enroll Roll No {target_emp.employee_code} in Face Registration first.",
                "enroll_url": url_for("attendance.face_registration_page", roll_no=target_emp.employee_code),
            }), 404
        try:
            stored_vector = json.loads(enr.protected_template)
            best_similarity = cosine_similarity(sample_vector, stored_vector)
            best_match = enr
        except Exception:
            return jsonify({"matched": False, "error": "Invalid biometric template format."}), 500
    else:
        # 1:N match across all enrolled profiles
        enrollments = FaceEnrollment.query.filter_by(enrollment_status="Enrolled").all()
        if not enrollments:
            return jsonify({
                "matched": False,
                "error": "No enrolled biometric profiles found in database. Please enroll workers with Roll No first."
            }), 404

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
            "employee_id": emp.id,
            "employee_name": emp.name,
            "employee_code": emp.employee_code,
            "roll_no": emp.employee_code,
            "job_role": emp.job_role,
            "status": "Present",
            "coffee_status": "Green Coffee",
            "warning": f"Duplicate event: Roll No {emp.employee_code} ({emp.name}) already recorded a {event_type} at {recent_dup.timestamp.strftime('%H:%M:%S UTC')}."
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
        created_by=f"{current_user.role} ({current_user.username})",
    )
    db.session.add(att_event)

    # Upsert daily attendance record as Green Coffee (Present)
    today = date.today()
    daily = DailyAttendance.query.filter_by(
        employee_id=emp.id,
        date=today,
        shift=shift
    ).first()

    if not daily:
        daily = DailyAttendance(
            employee_id=emp.id,
            date=today,
            shift=shift,
            status="Present",
            approved_by=f"Biometric Scan ({current_user.role} {current_user.username})",
            has_conflict=False,
        )
        db.session.add(daily)
    else:
        daily.status = "Present"
        daily.approved_by = f"Biometric Scan ({current_user.role} {current_user.username})"

    db.session.commit()

    log_audit(
        action="FACE_ATTENDANCE_VERIFIED",
        entity_type="AttendanceEvent",
        entity_id=str(emp.id),
        outcome="SUCCESS",
        details=f"Verified Roll No: {emp.employee_code} ({emp.name}) with {round(best_similarity * 100, 1)}% confidence by {current_user.role}. Marked Green Coffee (Present).",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    return jsonify({
        "matched": True,
        "confidence": round(best_similarity, 3),
        "employee_id": emp.id,
        "employee_name": emp.name,
        "employee_code": emp.employee_code,
        "roll_no": emp.employee_code,
        "job_role": emp.job_role,
        "status": "Present",
        "coffee_status": "Green Coffee",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "verified_by": f"{current_user.role} ({current_user.username})",
        "message": f"Verified Roll No: {emp.employee_code} — {emp.name}! Attendance recorded as ☕ Green Coffee (Present).",
    })
