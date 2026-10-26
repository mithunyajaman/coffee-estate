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

    @property
    def block_letter(self) -> str:
        """Extracts clean Block identifier (e.g. 'BLOCK A', 'BLOCK B', 'BLOCK C')."""
        if "block " in self.name.lower():
            part = self.name.split("-")[0].strip()
            return part.upper()
        return self.name.upper()

    @property
    def coffee_type(self) -> str:
        """Categorizes variety into 'Arabica Coffee', 'Robusta Coffee', 'Kaveri Coffee'."""
        v = (self.variety or "").lower()
        if "kaveri" in v or "cauvery" in v:
            return "Kaveri Coffee"
        elif "arabica" in v:
            return "Arabica Coffee"
        elif "robusta" in v:
            return "Robusta Coffee"
        return self.variety or "Specialty Coffee"

    @property
    def age_years(self):
        """Returns age of the plantation block in years if planting_date is set."""
        if self.planting_date:
            today = date.today()
            return today.year - self.planting_date.year - ((today.month, today.day) < (self.planting_date.month, self.planting_date.day))
        return None

    @property
    def variety_theme(self) -> dict:
        """Provides theme colors, icons, and description for clean visual display."""
        t = self.coffee_type
        if t == "Arabica Coffee":
            return {
                "key": "arabica",
                "name": "Arabica Coffee",
                "border_color": "#d97706",
                "bg_subtle": "#fffbeb",
                "text_color": "#78350f",
                "badge_bg": "#78350f",
                "accent_gradient": "linear-gradient(135deg, #78350f 0%, #b45309 100%)",
                "pill_badge": "bg-warning-subtle text-dark border border-warning",
                "icon": "bi-cup-hot-fill",
                "tagline": "Shade Grown (1,150m – 1,300m) • Mild, Aromatic & Acidic",
            }
        elif t == "Robusta Coffee":
            return {
                "key": "robusta",
                "name": "Robusta Coffee",
                "border_color": "#ca8a04",
                "bg_subtle": "#fefce8",
                "text_color": "#713f12",
                "badge_bg": "#854d0e",
                "accent_gradient": "linear-gradient(135deg, #854d0e 0%, #ca8a04 100%)",
                "pill_badge": "bg-warning-subtle text-dark border border-warning",
                "icon": "bi-shield-shaded",
                "tagline": "Warm Valley (900m – 1,100m) • Bold, High Crema & High Body",
            }
        elif t == "Kaveri Coffee":
            return {
                "key": "kaveri",
                "name": "Kaveri Coffee",
                "border_color": "#16a34a",
                "bg_subtle": "#f0fdf4",
                "text_color": "#14532d",
                "badge_bg": "#15803d",
                "accent_gradient": "linear-gradient(135deg, #15803d 0%, #166534 100%)",
                "pill_badge": "bg-success-subtle text-success border border-success",
                "icon": "bi-flower1",
                "tagline": "Catimor Hybrid (Cauvery) • Rust Resistant • High Yield Semi-Dwarf",
            }
        return {
            "key": "other",
            "name": self.variety or "Estate Coffee",
            "border_color": "#475569",
            "bg_subtle": "#f8fafc",
            "text_color": "#1e293b",
            "badge_bg": "#334155",
            "accent_gradient": "linear-gradient(135deg, #334155 0%, #475569 100%)",
            "pill_badge": "bg-secondary-subtle text-secondary border",
            "icon": "bi-tree-fill",
            "tagline": "Specialty Cultivar",
        }

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "block_letter": self.block_letter,
            "coffee_type": self.coffee_type,
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
