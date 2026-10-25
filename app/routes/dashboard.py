from datetime import datetime, timezone, date
from flask import Blueprint, render_template, jsonify, g
from sqlalchemy import func
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.services.auth_service import login_required, roles_required, get_current_user

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Page 3: Smart Dashboard Shell."""
    current_user = get_current_user()

    # Query real database records for KPIs
    total_employees = Employee.query.count()
    active_employees = Employee.query.filter_by(status="Active").count()
    total_users = User.query.count() if current_user.is_admin else None

    # Audit logs for manager/admin recent activity feed
    recent_audits = []
    if current_user.is_manager:
        recent_audits = (
            AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
        )

    # Empty states data structures for future modules (Blocks, Tasks, Harvest, Stock)
    kpis = {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "total_users": total_users,
        "active_blocks_count": 0,       # Stage 2 will populate from EstateBlocks
        "today_attendance_pct": 0,     # Stage 3 will populate from Attendance
        "today_present_count": 0,
        "harvest_this_month_kg": 0,    # Stage 2 will populate from HarvestRecords
        "pending_tasks_count": 0,      # Stage 2 will populate from Tasks
        "low_stock_items_count": 0,    # Stage 2 will populate from Inventory
    }

    freshness_timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")

    return render_template(
        "dashboard.html",
        current_user=current_user,
        kpis=kpis,
        recent_audits=recent_audits,
        freshness_timestamp=freshness_timestamp,
    )


@dashboard_bp.route("/api/dashboard/summary")
@login_required
def api_dashboard_summary():
    """Real-time summary API endpoint."""
    current_user = get_current_user()
    
    total_employees = Employee.query.count()
    active_employees = Employee.query.filter_by(status="Active").count()

    return jsonify({
        "data_freshness": datetime.now(timezone.utc).isoformat(),
        "user": {
            "username": current_user.username,
            "role": current_user.role,
        },
        "kpis": {
            "total_employees": total_employees,
            "active_employees": active_employees,
            "active_blocks": 0,
            "today_attendance": 0,
            "harvest_kg": 0,
            "pending_tasks": 0,
            "low_stock_alerts": 0,
        },
        "weather_demo": {
            "is_mock": True,
            "label": "DEMO MOCK - Chikmagalur Estate",
            "temperature_c": 24.5,
            "condition": "Partly Cloudy / Light Mist",
            "humidity_pct": 78,
            "rain_prob_pct": 20,
        }
    })


@dashboard_bp.route("/api/admin/audit-logs")
@roles_required("Admin")
def admin_audit_logs():
    """Admin-only API endpoint for viewing security audit logs (tests role enforcement)."""
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(50).all()
    return jsonify({
        "total": len(logs),
        "logs": [l.to_dict() for l in logs],
    })
