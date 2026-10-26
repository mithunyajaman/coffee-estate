from datetime import datetime, timezone, date
from app.database import db

class SprinklerLog(db.Model):
    __tablename__ = "sprinkler_logs"

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("estate_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    start_time = db.Column(db.String(10), nullable=False) # e.g. "06:30"
    end_time = db.Column(db.String(10), nullable=False)   # e.g. "11:30"
    duration_minutes = db.Column(db.Integer, nullable=False) # Total minutes sprinkler operated on this block
    sprinkler_type = db.Column(db.String(60), nullable=False, default="Overhead Rain-Gun") # Rain-Gun, Overhead Sprinkler, Drip, Hose-jet
    water_source = db.Column(db.String(100), nullable=False, default="Estate Lake / Stream") # Lake, Stream, Tank, Borewell
    equivalent_mm = db.Column(db.Numeric(6, 2), nullable=True, default=25.0) # Rainfall equivalent mm
    fuel_used_liters = db.Column(db.Numeric(6, 2), nullable=True) # Diesel/petrol used
    operator_name = db.Column(db.String(100), nullable=True) # Pump operator or supervisor
    purpose = db.Column(db.String(80), nullable=False, default="Blossom Shower Trigger") # Blossom, Backing, Soil Moisture
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship to EstateBlock
    block = db.relationship("EstateBlock", backref=db.backref("sprinkler_logs", lazy="dynamic", cascade="all, delete-orphan"))

    @property
    def duration_hours_str(self) -> str:
        """Formatted hours and minutes (e.g. 5h 00m)."""
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if hours > 0 and mins > 0:
            return f"{hours}h {mins}m"
        elif hours > 0:
            return f"{hours} hrs"
        return f"{mins} mins"

    def to_dict(self):
        return {
            "id": self.id,
            "block_id": self.block_id,
            "block_name": self.block.name if self.block else None,
            "block_letter": self.block.block_letter if self.block else None,
            "coffee_type": self.block.coffee_type if self.block else None,
            "date": self.date.isoformat(),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_minutes": self.duration_minutes,
            "duration_formatted": self.duration_hours_str,
            "sprinkler_type": self.sprinkler_type,
            "water_source": self.water_source,
            "equivalent_mm": float(self.equivalent_mm) if self.equivalent_mm is not None else None,
            "fuel_used_liters": float(self.fuel_used_liters) if self.fuel_used_liters is not None else None,
            "operator_name": self.operator_name,
            "purpose": self.purpose,
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<SprinklerLog Block {self.block_id} on {self.date}: {self.duration_minutes} mins>"


class RainfallRecord(db.Model):
    __tablename__ = "rainfall_records"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    rainfall_mm = db.Column(db.Numeric(6, 2), nullable=False) # Rain gauge reading in mm
    rain_type = db.Column(db.String(80), nullable=False, default="Blossom Showers") # Blossom Showers, Backing Showers, Southwest Monsoon, Northeast Monsoon, Summer Shower
    duration_hours = db.Column(db.Numeric(4, 1), nullable=True) # Duration of rainfall in hours
    recorded_by = db.Column(db.String(100), nullable=True) # Observer name / Supervisor
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "rainfall_mm": float(self.rainfall_mm),
            "rain_type": self.rain_type,
            "duration_hours": float(self.duration_hours) if self.duration_hours is not None else None,
            "recorded_by": self.recorded_by,
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<RainfallRecord {self.date}: {self.rainfall_mm}mm ({self.rain_type})>"
