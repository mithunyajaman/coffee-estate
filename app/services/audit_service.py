from flask import request, has_request_context
from app.database import db
from app.models.audit import AuditLog

def log_audit(
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    outcome: str = "SUCCESS",
    details: str | None = None,
    actor_id: int | None = None,
    actor_username: str | None = None,
) -> AuditLog:
    """Safely log security and administrative events to database."""
    ip_addr = None
    ua = None

    if has_request_context():
        # Handle proxy headers safely
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_addr = forwarded.split(",")[0].strip()
        else:
            ip_addr = request.remote_addr
        ua = (request.user_agent.string or "")[:250] if request.user_agent else None

        # Fallback to session user if not passed
        from flask import session
        if actor_id is None and "user_id" in session:
            actor_id = session.get("user_id")
        if actor_username is None and "username" in session:
            actor_username = session.get("username")

    try:
        log_entry = AuditLog(
            actor_id=actor_id,
            actor_username=actor_username or "System",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            outcome=outcome,
            details=details,
            ip_address=ip_addr,
            user_agent=ua,
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry
    except Exception as e:
        db.session.rollback()
        # Fallback to avoid breaking application if logging fails
        print(f"[AuditLog Error] Failed to persist audit log: {e}")
        return None
