import csv
import io
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify
from sqlalchemy import func
from app.database import db
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit
from app.models.farm import EstateBlock
from app.models.weather_sprinkler import SprinklerLog, RainfallRecord

weather_bp = Blueprint("weather", __name__)

# ==============================================================================
# 1. WEATHER & RAINFALL (SEPARATE PAGE)
# ==============================================================================

@weather_bp.route("/weather", methods=["GET"])
@weather_bp.route("/weather/", methods=["GET"])
@login_required
def weather_index():
    """Page 5: Weather & Rainfall Intelligence."""
    current_user = get_current_user()
    today = date.today()

    # Rainfall records & aggregations
    rainfall_records = RainfallRecord.query.order_by(RainfallRecord.date.desc()).all()

    total_season_rainfall_mm = db.session.query(func.coalesce(func.sum(RainfallRecord.rainfall_mm), 0)).scalar() or 0.0
    blossom_rainfall_mm = db.session.query(
        func.coalesce(func.sum(RainfallRecord.rainfall_mm), 0)
    ).filter(RainfallRecord.rain_type.ilike("%blossom%")).scalar() or 0.0
    backing_rainfall_mm = db.session.query(
        func.coalesce(func.sum(RainfallRecord.rainfall_mm), 0)
    ).filter(RainfallRecord.rain_type.ilike("%backing%")).scalar() or 0.0

    # 7-Day Agronomic Forecast
    forecast = [
        {"day": "Today", "date": today.strftime("%d %b"), "temp_high": 27, "temp_low": 18, "humidity": 78, "rain_chance": 20, "condition": "Partly Sunny", "icon": "bi-sun", "spray_advice": "Ideal for Copper Oxychloride Spraying"},
        {"day": "Tomorrow", "date": (today + timedelta(days=1)).strftime("%d %b"), "temp_high": 26, "temp_low": 18, "humidity": 82, "rain_chance": 35, "condition": "Misty Morning, Afternoon Sun", "icon": "bi-cloud-sun", "spray_advice": "Good for Canopy Pruning"},
        {"day": (today + timedelta(days=2)).strftime("%A"), "date": (today + timedelta(days=2)).strftime("%d %b"), "temp_high": 25, "temp_low": 17, "humidity": 85, "rain_chance": 50, "condition": "Scattered Showers", "icon": "bi-cloud-drizzle", "spray_advice": "Avoid chemical spray before rain"},
        {"day": (today + timedelta(days=3)).strftime("%A"), "date": (today + timedelta(days=3)).strftime("%d %b"), "temp_high": 24, "temp_low": 17, "humidity": 88, "rain_chance": 65, "condition": "Moderate Monsoon Showers", "icon": "bi-cloud-rain", "spray_advice": "Monitor drain channels & stream"},
        {"day": (today + timedelta(days=4)).strftime("%A"), "date": (today + timedelta(days=4)).strftime("%d %b"), "temp_high": 25, "temp_low": 18, "humidity": 84, "rain_chance": 40, "condition": "Overcast", "icon": "bi-clouds", "spray_advice": "Inspect leaves for Rust spore formation"},
        {"day": (today + timedelta(days=5)).strftime("%A"), "date": (today + timedelta(days=5)).strftime("%d %b"), "temp_high": 26, "temp_low": 18, "humidity": 79, "rain_chance": 25, "condition": "Pleasant Sun", "icon": "bi-sun", "spray_advice": "Suitable for Fertilizer broadcast"},
        {"day": (today + timedelta(days=6)).strftime("%A"), "date": (today + timedelta(days=6)).strftime("%d %b"), "temp_high": 27, "temp_low": 19, "humidity": 75, "rain_chance": 15, "condition": "Clear Blue Skies", "icon": "bi-brightness-high", "spray_advice": "Optimal for Cherry picking & Sun drying"},
    ]

    return render_template(
        "weather.html",
        rainfall_records=rainfall_records,
        forecast=forecast,
        total_season_rainfall_mm=float(total_season_rainfall_mm),
        blossom_rainfall_mm=float(blossom_rainfall_mm),
        backing_rainfall_mm=float(backing_rainfall_mm),
        date_today=today.isoformat(),
        current_user=current_user
    )


@weather_bp.route("/weather/rainfall/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_rainfall_record():
    """Logs daily rain gauge reading."""
    current_user = get_current_user()
    date_str = request.form.get("date")
    rainfall_mm = request.form.get("rainfall_mm", type=float)
    rain_type = request.form.get("rain_type") or "Blossom Showers"
    duration_hours = request.form.get("duration_hours", type=float)
    recorded_by = request.form.get("recorded_by") or current_user.username
    notes = request.form.get("notes") or ""

    if rainfall_mm is None or rainfall_mm < 0:
        flash("Please enter a valid rainfall measurement in mm.", "danger")
        return redirect(url_for("weather.weather_index"))

    try:
        r_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    except ValueError:
        r_date = date.today()

    record = RainfallRecord(
        date=r_date,
        rainfall_mm=rainfall_mm,
        rain_type=rain_type,
        duration_hours=duration_hours,
        recorded_by=recorded_by,
        notes=notes
    )
    db.session.add(record)
    db.session.commit()

    log_audit("RAINFALL_RECORD_ADDED", f"Logged {rainfall_mm}mm {rain_type} on {r_date}", current_user.id)
    flash(f"Rainfall record added: {rainfall_mm} mm ({rain_type}) on {r_date.strftime('%d %b %Y')}!", "success")
    return redirect(url_for("weather.weather_index"))


@weather_bp.route("/weather/rainfall/delete/<int:record_id>", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def delete_rainfall_record(record_id):
    """Deletes a rainfall record."""
    current_user = get_current_user()
    record = RainfallRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()

    log_audit("RAINFALL_RECORD_DELETED", f"Deleted rainfall record #{record_id}", current_user.id)
    flash("Rainfall record deleted successfully.", "info")
    return redirect(url_for("weather.weather_index"))


@weather_bp.route("/weather/rainfall/export-csv")
@login_required
def export_rainfall_csv():
    """Exports rain gauge records to CSV."""
    records = RainfallRecord.query.order_by(RainfallRecord.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record ID",
        "Date",
        "Rainfall (mm)",
        "Rain Type",
        "Duration (Hours)",
        "Recorded By",
        "Notes"
    ])

    for r in records:
        writer.writerow([
            r.id,
            r.date.isoformat(),
            r.rainfall_mm,
            r.rain_type,
            r.duration_hours or "",
            r.recorded_by or "",
            r.notes or ""
        ])

    output.seek(0)
    filename = f"estate_rainfall_records_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# 2. SPRINKLER & IRRIGATION WATER (SEPARATE PAGE)
# ==============================================================================

@weather_bp.route("/sprinkler", methods=["GET"])
@weather_bp.route("/sprinkler/", methods=["GET"])
@weather_bp.route("/irrigation", methods=["GET"])
@weather_bp.route("/irrigation/", methods=["GET"])
@login_required
def sprinkler_index():
    """Separate Dedicated Page for Sprinkler & Irrigation Water Management."""
    current_user = get_current_user()
    today = date.today()

    block_filter = request.args.get("block_id", type=int)
    date_filter = request.args.get("date", "").strip()

    sprinkler_query = SprinklerLog.query
    if block_filter:
        sprinkler_query = sprinkler_query.filter_by(block_id=block_filter)
    if date_filter:
        try:
            d_val = datetime.strptime(date_filter, "%Y-%m-%d").date()
            sprinkler_query = sprinkler_query.filter_by(date=d_val)
        except ValueError:
            pass

    sprinkler_logs = sprinkler_query.order_by(SprinklerLog.date.desc(), SprinklerLog.id.desc()).all()
    all_blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()

    total_sprinkler_minutes = sum(s.duration_minutes for s in sprinkler_logs)
    total_sprinkler_hours = round(total_sprinkler_minutes / 60.0, 1)

    unique_blocks_irrigated = len(set(s.block_id for s in sprinkler_logs))
    total_equivalent_water_mm = sum(float(s.equivalent_mm or 0) for s in sprinkler_logs)
    total_diesel_liters = sum(float(s.fuel_used_liters or 0) for s in sprinkler_logs)
    last_sprinkler = SprinklerLog.query.order_by(SprinklerLog.date.desc(), SprinklerLog.id.desc()).first()

    return render_template(
        "sprinkler.html",
        sprinkler_logs=sprinkler_logs,
        all_blocks=all_blocks,
        total_sprinkler_minutes=total_sprinkler_minutes,
        total_sprinkler_hours=total_sprinkler_hours,
        unique_blocks_irrigated=unique_blocks_irrigated,
        total_equivalent_water_mm=round(total_equivalent_water_mm, 1),
        total_diesel_liters=round(total_diesel_liters, 1),
        last_sprinkler=last_sprinkler,
        block_filter=block_filter,
        date_filter=date_filter,
        date_today=today.isoformat(),
        current_user=current_user
    )


@weather_bp.route("/sprinkler/add", methods=["POST"])
@weather_bp.route("/weather/sprinkler/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_sprinkler_log():
    """Logs sprinkler irrigation details (when, what time, for one block how much minutes)."""
    current_user = get_current_user()

    block_id = request.form.get("block_id", type=int)
    date_str = request.form.get("date")
    start_time = (request.form.get("start_time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    duration_minutes = request.form.get("duration_minutes", type=int)

    sprinkler_type = request.form.get("sprinkler_type") or "Overhead Rain-Gun"
    water_source = request.form.get("water_source") or "Estate Lake / Stream"
    equivalent_mm = request.form.get("equivalent_mm", type=float) or 25.0
    fuel_used_liters = request.form.get("fuel_used_liters", type=float)
    operator_name = (request.form.get("operator_name") or "").strip() or current_user.username
    purpose = request.form.get("purpose") or "Blossom Shower Trigger"
    notes = (request.form.get("notes") or "").strip()

    if not block_id:
        flash("Please select a target plantation block.", "danger")
        return redirect(url_for("weather.sprinkler_index"))

    block = EstateBlock.query.get(block_id)
    if not block:
        flash("Selected block not found.", "danger")
        return redirect(url_for("weather.sprinkler_index"))

    try:
        log_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    except ValueError:
        log_date = date.today()

    if not duration_minutes and start_time and end_time:
        try:
            t1 = datetime.strptime(start_time, "%H:%M")
            t2 = datetime.strptime(end_time, "%H:%M")
            diff = (t2 - t1).total_seconds() / 60
            if diff < 0:
                diff += 24 * 60
            duration_minutes = int(diff)
        except ValueError:
            duration_minutes = 60
    elif not duration_minutes:
        duration_minutes = 60

    log = SprinklerLog(
        block_id=block.id,
        date=log_date,
        start_time=start_time or "07:00",
        end_time=end_time or "11:00",
        duration_minutes=max(1, duration_minutes),
        sprinkler_type=sprinkler_type,
        water_source=water_source,
        equivalent_mm=equivalent_mm,
        fuel_used_liters=fuel_used_liters,
        operator_name=operator_name,
        purpose=purpose,
        notes=notes
    )
    db.session.add(log)
    db.session.commit()

    log_audit("SPRINKLER_LOG_ADDED", f"Logged {duration_minutes} mins sprinkler on {block.name}", current_user.id)
    flash(f"Sprinkler run logged for {block.name}: {duration_minutes} minutes ({log.duration_hours_str}) from {log.start_time} to {log.end_time}!", "success")
    return redirect(url_for("weather.sprinkler_index"))


@weather_bp.route("/sprinkler/delete/<int:log_id>", methods=["POST"])
@weather_bp.route("/weather/sprinkler/delete/<int:log_id>", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def delete_sprinkler_log(log_id):
    """Deletes a sprinkler record."""
    current_user = get_current_user()
    log = SprinklerLog.query.get_or_404(log_id)
    block_name = log.block.name if log.block else f"Block {log.block_id}"

    db.session.delete(log)
    db.session.commit()

    log_audit("SPRINKLER_LOG_DELETED", f"Deleted sprinkler log #{log_id} on {block_name}", current_user.id)
    flash("Sprinkler record deleted successfully.", "info")
    return redirect(url_for("weather.sprinkler_index"))


@weather_bp.route("/sprinkler/export-csv")
@weather_bp.route("/weather/sprinkler/export-csv")
@login_required
def export_sprinkler_csv():
    """Exports sprinkler irrigation logs to CSV."""
    logs = SprinklerLog.query.order_by(SprinklerLog.date.desc(), SprinklerLog.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record ID",
        "Date",
        "Block Letter",
        "Block Name",
        "Coffee Variety",
        "Start Time",
        "End Time",
        "Duration Minutes",
        "Duration Formatted",
        "Sprinkler Type",
        "Water Source",
        "Rain Equivalent (mm)",
        "Fuel Used (Liters)",
        "Operator Name",
        "Purpose",
        "Notes"
    ])

    for s in logs:
        writer.writerow([
            s.id,
            s.date.isoformat(),
            s.block.block_letter if s.block else "",
            s.block.name if s.block else "",
            s.block.coffee_type if s.block else "",
            s.start_time,
            s.end_time,
            s.duration_minutes,
            s.duration_hours_str,
            s.sprinkler_type,
            s.water_source,
            s.equivalent_mm or "",
            s.fuel_used_liters or "",
            s.operator_name or "",
            s.purpose,
            s.notes or ""
        ])

    output.seek(0)
    filename = f"estate_sprinkler_records_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
