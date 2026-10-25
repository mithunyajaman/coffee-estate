from functools import wraps
from datetime import datetime, timezone
from flask import session, redirect, url_for, request, jsonify, flash, abort, g
from app.database import db
from app.models.user import User
from app.services.audit_service import log_audit

def get_current_user() -> User | None:
    """Retrieve verified current user from database based on server session ID."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    user = db.session.get(User, user_id)
    if not user or user.status != "Active":
        # Invalidate stale or deactivated session
        session.clear()
        return None

    return user


def login_user(user: User) -> None:
    """Set server session securely and record login audit."""
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    session.permanent = True

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    log_audit(
        action="LOGIN_SUCCESS",
        entity_type="User",
        entity_id=str(user.id),
        outcome="SUCCESS",
        details=f"User {user.username} logged in with role {user.role}",
        actor_id=user.id,
        actor_username=user.username,
    )


def logout_user() -> None:
    """Clear session and log audit."""
    user = get_current_user()
    if user:
        log_audit(
            action="LOGOUT",
            entity_type="User",
            entity_id=str(user.id),
            outcome="SUCCESS",
            details=f"User {user.username} logged out",
            actor_id=user.id,
            actor_username=user.username,
        )
    session.clear()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized: login required"}), 401
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*allowed_roles):
    """Enforce strict server-side role check from database (never trust client claims)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "Unauthorized: login required"}), 401
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for("auth.login", next=request.url))

            if user.role not in allowed_roles:
                log_audit(
                    action="ROLE_ACCESS_DENIED",
                    entity_type="Security",
                    entity_id=str(user.id),
                    outcome="DENIED",
                    details=f"User {user.username} (Role: {user.role}) denied access to {request.path}. Required: {list(allowed_roles)}",
                    actor_id=user.id,
                    actor_username=user.username,
                )
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Forbidden",
                        "message": "You do not have permission to access this resource."
                    }), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
