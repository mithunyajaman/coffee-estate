from datetime import datetime, timezone, date, timedelta
from app.database import db

class PesticideApplication(db.Model):
    """Logs agricultural chemical and biological spraying applications with safety intervals."""
    __tablename__ = "pesticide_applications"

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("estate_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    
    pesticide_name = db.Column(db.String(150), nullable=False) # e.g. "Copper Oxychloride 50% WP (Bordeaux Spray)"
    category = db.Column(db.String(50), nullable=False, default="Fungicide") # Fungicide, Insecticide, Bio-pesticide, Herbicide, Nematicide
    target_pest = db.Column(db.String(120), nullable=False) # Coffee Leaf Rust, Coffee Berry Borer, White Stem Borer, Black Rot, Mealybug
    
    dosage = db.Column(db.String(100), nullable=False) # e.g. "500g per 200L water (0.25%)"
    quantity_used = db.Column(db.Numeric(10, 2), nullable=False, default=0.0) # Quantity of concentrate or solution
    unit = db.Column(db.String(20), nullable=False, default="kg") # kg, Liters, ml, grams, Bags
    
    # Bags & Weight in kg tracking
    bags_count = db.Column(db.Integer, nullable=True, default=1) # Number of bags / containers
    bag_weight_kg = db.Column(db.Numeric(10, 2), nullable=True, default=0.0) # Weight per individual bag in kg
    total_weight_kg = db.Column(db.Numeric(10, 2), nullable=True, default=0.0) # Total weight in kg (bags_count * bag_weight_kg or total kg applied)
    
    application_method = db.Column(db.String(80), nullable=False, default="Knapsack Sprayer") # Knapsack Sprayer, Tractor Mist Blower, Stem Painting, Drenching
    
    # Safety & Compliance Intervals
    pre_harvest_interval_days = db.Column(db.Integer, nullable=False, default=14) # PHI: Days before harvesting permitted
    re_entry_interval_hours = db.Column(db.Integer, nullable=False, default=24)    # REI: Hours before workers safely enter block
    weather_condition = db.Column(db.String(80), nullable=True) # Clear & Dry, Overcast, Mild Breeze
    safety_ppe = db.Column(db.String(180), nullable=True, default="N95 respirator, chemical apron, nitrile gloves, eye goggles")
    
    # Traceability & Stores
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    operator_name = db.Column(db.String(100), nullable=True) # Spraying gang lead
    supervised_by = db.Column(db.String(100), nullable=True) # Field manager / Agronomist
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    block = db.relationship("EstateBlock", backref=db.backref("pesticide_applications", lazy="dynamic", cascade="all, delete-orphan"))
    inventory_item = db.relationship("InventoryItem", backref=db.backref("pesticide_usages", lazy="dynamic"))

    @property
    def safe_harvest_date(self) -> date:
        """Returns the earliest date when coffee cherries can be picked safely without chemical residue."""
        return self.date + timedelta(days=self.pre_harvest_interval_days)

    @property
    def is_within_phi(self) -> bool:
        """Returns True if block is currently in Pre-Harvest chemical quarantine."""
        return date.today() < self.safe_harvest_date

    @property
    def phi_remaining_days(self) -> int:
        """Remaining quarantine days before cherries can be safely harvested."""
        rem = (self.safe_harvest_date - date.today()).days
        return max(0, rem)

    @property
    def computed_weight_kg(self) -> float:
        """Returns the total weight in kg, calculated from bags * bag_weight_kg or total_weight_kg/quantity_used."""
        if self.total_weight_kg and float(self.total_weight_kg) > 0:
            return float(self.total_weight_kg)
        if self.bags_count and self.bag_weight_kg and float(self.bag_weight_kg) > 0:
            return round(int(self.bags_count) * float(self.bag_weight_kg), 2)
        if self.unit and self.unit.lower() == "kg":
            return float(self.quantity_used)
        return float(self.quantity_used)

    def to_dict(self):
        return {
            "id": self.id,
            "block_id": self.block_id,
            "block_name": self.block.name if self.block else None,
            "date": self.date.isoformat() if self.date else None,
            "pesticide_name": self.pesticide_name,
            "category": self.category,
            "target_pest": self.target_pest,
            "dosage": self.dosage,
            "quantity_used": float(self.quantity_used),
            "unit": self.unit,
            "bags_count": self.bags_count or 1,
            "bag_weight_kg": float(self.bag_weight_kg or 0.0),
            "total_weight_kg": float(self.computed_weight_kg),
            "application_method": self.application_method,
            "pre_harvest_interval_days": self.pre_harvest_interval_days,
            "safe_harvest_date": self.safe_harvest_date.isoformat(),
            "is_within_phi": self.is_within_phi,
            "phi_remaining_days": self.phi_remaining_days,
            "re_entry_interval_hours": self.re_entry_interval_hours,
            "weather_condition": self.weather_condition,
            "operator_name": self.operator_name,
            "supervised_by": self.supervised_by,
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<PesticideApplication {self.pesticide_name} on Block {self.block_id} ({self.date})>"
