from datetime import datetime, timezone, date
from flask import Blueprint, render_template, jsonify, g, session
from sqlalchemy import func
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.models.farm import EstateBlock
from app.models.harvest import HarvestRecord
from app.models.task import Task
from app.models.inventory import InventoryItem
from app.models.attendance import DailyAttendance, AttendanceEvent
from app.models.weather_sprinkler import SprinklerLog, RainfallRecord
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.geo_weather_service import get_district_weather

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
    active_blocks = EstateBlock.query.filter_by(status="Active").count()
    total_harvest_kg = db.session.query(func.coalesce(func.sum(HarvestRecord.actual_quantity), 0)).scalar()
    pending_tasks = Task.query.filter_by(status="Pending").count()
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_balance <= InventoryItem.reorder_level).count()
    today = date.today()
    today_present = DailyAttendance.query.filter_by(date=today, status="Present").count()
    attendance_pct = round((today_present / active_employees * 100), 1) if active_employees > 0 else 0

    # Sprinkler & Irrigation Telemetry
    total_sprinkler_minutes = db.session.query(func.coalesce(func.sum(SprinklerLog.duration_minutes), 0)).scalar() or 0
    sprinkler_runs_count = SprinklerLog.query.count()
    latest_sprinkler_run = SprinklerLog.query.order_by(SprinklerLog.date.desc(), SprinklerLog.id.desc()).first()

    # Farm blocks list for visual block deck
    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).limit(4).all()

    # Recent face biometric punches today
    today_face_punches = (
        AttendanceEvent.query.filter_by(method="Face")
        .order_by(AttendanceEvent.timestamp.desc())
        .limit(5)
        .all()
    )

    # Weather telemetry for selected location
    selected_state = session.get("selected_state", "Karnataka")
    selected_district = session.get("selected_district", "Chikmagalur")
    weather_info = get_district_weather(selected_state, selected_district)

    # Audit logs for manager/admin recent activity feed
    recent_audits = []
    if current_user.is_manager:
        recent_audits = (
            AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
        )

    kpis = {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "total_users": total_users,
        "active_blocks_count": active_blocks,
        "today_attendance_pct": attendance_pct,
        "today_present_count": today_present,
        "harvest_this_month_kg": float(total_harvest_kg or 0.0),
        "pending_tasks_count": pending_tasks,
        "low_stock_items_count": low_stock_items,
        "total_sprinkler_minutes": int(total_sprinkler_minutes),
        "total_sprinkler_hours": round(total_sprinkler_minutes / 60.0, 1),
        "sprinkler_runs_count": sprinkler_runs_count,
    }

    freshness_timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")

    return render_template(
        "dashboard.html",
        current_user=current_user,
        kpis=kpis,
        weather_info=weather_info,
        blocks=blocks,
        today_face_punches=today_face_punches,
        latest_sprinkler_run=latest_sprinkler_run,
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
