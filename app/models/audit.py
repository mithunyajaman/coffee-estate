from datetime import datetime, timezone
from app.database import db

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    actor_username = db.Column(db.String(80), nullable=True)
    action = db.Column(db.String(80), nullable=False, index=True)  # LOGIN_SUCCESS, LOGIN_FAILURE, ROLE_BYPASS_ATTEMPT, etc.
    entity_type = db.Column(db.String(60), nullable=True)         # User, Employee, Session
    entity_id = db.Column(db.String(80), nullable=True)
    outcome = db.Column(db.String(20), nullable=False, default="SUCCESS")  # SUCCESS, FAILURE, DENIED
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(60), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_username": self.actor_username,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "outcome": self.outcome,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.actor_username or 'System'} [{self.outcome}]>"
