from flask import Blueprint, render_template, jsonify
from sqlalchemy import text
from app.database import db
from app.services.auth_service import get_current_user

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    """Page 1: Loading Screen with estate background and progressive loader."""
    user = get_current_user()
    return render_template("loading.html", current_user=user)

@main_bp.route("/api/health")
def health_check():
    """System health check endpoint verifying database connectivity."""
    db_status = "connected"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    user = get_current_user()
    return jsonify({
        "status": "healthy" if "error" not in db_status else "degraded",
        "system": "AI-Powered Smart Coffee Estate Management System",
        "database": db_status,
        "authenticated": user is not None,
        "role": user.role if user else None,
    })
