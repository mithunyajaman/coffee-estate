from datetime import datetime, timezone, date
from app.database import db

class HarvestRecord(db.Model):
    __tablename__ = "harvest_records"

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("estate_blocks.id", ondelete="RESTRICT"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    planned_quantity = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) # kg
    actual_quantity = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # kg
    unit = db.Column(db.String(20), nullable=False, default="kg")
    team_id = db.Column(db.String(80), nullable=True) # e.g. "Team Alpha (12 Pickers)", "East Slope Gang"
    processing_status = db.Column(db.String(50), nullable=False, default="Raw Cherry") # Raw Cherry, Wet Pulped, Dry Natural, Parchment
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def variance_kg(self):
        """Variance: Actual - Planned."""
        act = float(self.actual_quantity or 0)
        plan = float(self.planned_quantity or 0)
        return act - plan

    def to_dict(self):
        return {
            "id": self.id,
            "block_id": self.block_id,
            "block_name": self.block.name if self.block else None,
            "date": self.date.isoformat() if self.date else None,
            "planned_quantity": float(self.planned_quantity),
            "actual_quantity": float(self.actual_quantity),
            "unit": self.unit,
            "team_id": self.team_id,
            "processing_status": self.processing_status,
            "notes": self.notes,
            "variance_kg": self.variance_kg,
        }

    def __repr__(self):
        return f"<HarvestRecord Block {self.block_id} - {self.actual_quantity}{self.unit}>"
