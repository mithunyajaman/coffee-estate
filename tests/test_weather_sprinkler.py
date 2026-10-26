import pytest
from datetime import date
from app.database import db
from app.models.weather_sprinkler import SprinklerLog, RainfallRecord
from app.models.farm import EstateBlock

def test_weather_page_load(client, auth_client, app):
    """Test /weather page loads for authenticated users."""
    auth_client.login_manager()
    res = client.get("/weather")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Weather" in html
    assert "Sprinkler" in html

def test_add_sprinkler_log_with_minutes(client, auth_client, app):
    """Test logging a sprinkler run with date, start/end time, and duration in minutes."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Block A - Arabica", area=12.5, unit="Hectares", variety="Arabica")
            db.session.add(block)
            db.session.commit()
        block_id = block.id

    auth_client.login_manager()
    res = client.post(
        "/weather/sprinkler/add",
        data={
            "block_id": str(block_id),
            "date": "2026-10-27",
            "start_time": "06:30",
            "end_time": "11:30",
            "duration_minutes": "300",
            "sprinkler_type": "Overhead Rain-Gun (Rotary 2.5 bar)",
            "water_source": "Estate Lake / Bhadra Stream",
            "equivalent_mm": "25.0",
            "fuel_used_liters": "14.5",
            "operator_name": "Suresh Pump Operator",
            "purpose": "Blossom Shower Trigger",
            "notes": "Verified sprinkler coverage across block",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        log = SprinklerLog.query.filter_by(duration_minutes=300).order_by(SprinklerLog.id.desc()).first()
        assert log is not None
        assert log.start_time == "06:30"
        assert log.end_time == "11:30"
        assert log.duration_minutes == 300
        assert log.duration_hours_str == "5 hrs"
        assert log.block_id == block_id

def test_add_rainfall_record(client, auth_client, app):
    """Test adding rain gauge measurement."""
    auth_client.login_manager()
    res = client.post(
        "/weather/rainfall/add",
        data={
            "date": "2026-10-27",
            "rainfall_mm": "42.5",
            "rain_type": "Blossom Showers",
            "duration_hours": "3.5",
            "recorded_by": "Deepak Kulkarni",
            "notes": "Optimal blossom triggering rain",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        rain = RainfallRecord.query.filter_by(rainfall_mm=42.5).first()
        assert rain is not None
        assert rain.rain_type == "Blossom Showers"

def test_worker_cannot_add_sprinkler_log(client, auth_client, app):
    """Regular workers cannot add sprinkler records (403 Forbidden)."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Block A - Arabica", area=12.5, unit="Hectares", variety="Arabica")
            db.session.add(block)
            db.session.commit()
        block_id = block.id

    auth_client.login_employee()
    res = client.post(
        "/weather/sprinkler/add",
        data={
            "block_id": str(block_id),
            "date": "2026-10-27",
            "start_time": "08:00",
            "end_time": "10:00",
            "duration_minutes": "120",
        },
    )
    assert res.status_code == 403

def test_export_sprinkler_and_rainfall_csv(client, auth_client):
    """Test CSV export downloads."""
    auth_client.login_manager()
    res_s = client.get("/weather/sprinkler/export-csv")
    assert res_s.status_code == 200
    assert "text/csv" in res_s.content_type
    assert "Duration Minutes" in res_s.data.decode("utf-8")

    res_r = client.get("/weather/rainfall/export-csv")
    assert res_r.status_code == 200
    assert "text/csv" in res_r.content_type
    assert "Rainfall (mm)" in res_r.data.decode("utf-8")
