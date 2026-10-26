from datetime import datetime, timezone, date
from app.database import db

class DailyAttendance(db.Model):
    __tablename__ = "daily_attendance"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    shift = db.Column(db.String(30), nullable=False, default="Morning Shift") # Morning Shift, General Shift, Afternoon Shift
    status = db.Column(db.String(30), nullable=False, default="Present")       # Present, Absent, Half-day, On Leave
    approved_by = db.Column(db.String(100), nullable=True) # Manager name
    correction_reason = db.Column(db.String(255), nullable=True)
    has_conflict = db.Column(db.Boolean, default=False, nullable=False) # For offline sync conflict flagging
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    employee = db.relationship("Employee", backref="daily_attendances")

    # Unique constraint per employee, date, and shift to ensure idempotency
    __table_args__ = (
        db.UniqueConstraint("employee_id", "date", "shift", name="uq_emp_date_shift"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_code": self.employee.employee_code if self.employee else None,
            "employee_name": self.employee.name if self.employee else None,
            "date": self.date.isoformat() if self.date else None,
            "shift": self.shift,
            "status": self.status,
            "approved_by": self.approved_by,
            "correction_reason": self.correction_reason,
            "has_conflict": self.has_conflict,
        }

    def __repr__(self):
        return f"<DailyAttendance Emp:{self.employee_id} {self.date} [{self.status}]>"


class AttendanceEvent(db.Model):
    """Raw clock-in / clock-out events from face verification, manual roster, or offline sync."""
    __tablename__ = "attendance_events"

    id = db.Column(db.Integer, primary_key=True)
    event_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True) # For idempotent offline queue sync
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = db.Column(db.String(30), nullable=False, default="Check-in") # Check-in, Check-out
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    method = db.Column(db.String(30), nullable=False, default="Manual") # Face, Manual, Offline_Sync
    confidence = db.Column(db.Float, nullable=True) # Confidence percentage (e.g. 0.94)
    device_id = db.Column(db.String(80), nullable=True) # Browser / Tablet ID
    sync_status = db.Column(db.String(30), nullable=False, default="Synced") # Synced, Conflict, Pending_Review
    created_by = db.Column(db.String(100), nullable=True)

    employee = db.relationship("Employee", backref="attendance_events")

    def to_dict(self):
        return {
            "id": self.id,
            "event_uuid": self.event_uuid,
            "employee_id": self.employee_id,
            "employee_code": self.employee.employee_code if self.employee else None,
            "employee_name": self.employee.name if self.employee else None,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "method": self.method,
            "confidence": self.confidence,
            "device_id": self.device_id,
            "sync_status": self.sync_status,
            "created_by": self.created_by,
        }

    def __repr__(self):
        return f"<AttendanceEvent {self.event_type} Emp:{self.employee_id} via {self.method}>"


class FaceEnrollment(db.Model):
    """Stores biometric consent and mathematical feature template reference (NOT raw face images)."""
    __tablename__ = "face_enrollments"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    consent_status = db.Column(db.Boolean, nullable=False, default=False) # Explicit user consent
    consent_timestamp = db.Column(db.DateTime, nullable=True)
    protected_template = db.Column(db.Text, nullable=False) # Mathematical embedding vector (JSON)
    enrollment_status = db.Column(db.String(30), nullable=False, default="Enrolled") # Enrolled, Revoked, Re-scan Needed
    confidence_threshold = db.Column(db.Float, nullable=False, default=0.75) # Default matching threshold
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    employee = db.relationship("Employee", backref=db.backref("face_enrollment", uselist=False))

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_code": self.employee.employee_code if self.employee else None,
            "employee_name": self.employee.name if self.employee else None,
            "consent_status": self.consent_status,
            "enrollment_status": self.enrollment_status,
            "confidence_threshold": self.confidence_threshold,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<FaceEnrollment Emp:{self.employee_id} [{self.enrollment_status}]>"
