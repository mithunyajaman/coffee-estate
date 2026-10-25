from datetime import datetime, timezone, date
from app.database import db

class EstateBlock(db.Model):
    __tablename__ = "estate_blocks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True) # e.g. "Block A - Arabica Ridge"
    area = db.Column(db.Numeric(8, 2), nullable=False) # e.g. 12.50
    unit = db.Column(db.String(20), nullable=False, default="Hectares") # Hectares or Acres
    variety = db.Column(db.String(100), nullable=False) # e.g. "Arabica Chandragiri", "Robusta CxR", "S.795"
    planting_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(150), nullable=True) # e.g. "North Slope, 1150m ASL"
    status = db.Column(db.String(30), nullable=False, default="Active") # Active, Maintenance, Fallow, Replanting
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    activities = db.relationship("FarmActivity", backref="block", cascade="all, delete-orphan", lazy="dynamic")
    harvest_records = db.relationship("HarvestRecord", backref="block", lazy="dynamic")
    tasks = db.relationship("Task", backref="block", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "area": float(self.area) if self.area is not None else 0.0,
            "unit": self.unit,
            "variety": self.variety,
            "planting_date": self.planting_date.isoformat() if self.planting_date else None,
            "location": self.location,
            "status": self.status,
            "activities_count": self.activities.count(),
        }

    def __repr__(self):
        return f"<EstateBlock {self.name} ({self.variety})>"


class FarmActivity(db.Model):
    __tablename__ = "farm_activities"

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("estate_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = db.Column(db.String(80), nullable=False) # Pruning, Fertilizer, Irrigation, Pest Inspection, Shade Lopping, Weeding
    date = db.Column(db.Date, nullable=False, default=date.today)
    input_quantity = db.Column(db.String(100), nullable=True) # e.g. "150 kg NPK 17-17-17", "2000 L Drip"
    notes = db.Column(db.Text, nullable=True)
    responsible_user = db.Column(db.String(100), nullable=True) # User or Supervisor name
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "block_id": self.block_id,
            "block_name": self.block.name if self.block else None,
            "activity_type": self.activity_type,
            "date": self.date.isoformat() if self.date else None,
            "input_quantity": self.input_quantity,
            "notes": self.notes,
            "responsible_user": self.responsible_user,
        }

    def __repr__(self):
        return f"<FarmActivity {self.activity_type} on Block {self.block_id}>"
