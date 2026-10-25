from datetime import datetime, timezone, date
from app.database import db

class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True) # e.g. "NPK 17-17-17 Fertilizer"
    category = db.Column(db.String(60), nullable=False) # Fertilizer, Crop Protection, Fuel, Equipment, Packaging
    unit = db.Column(db.String(30), nullable=False)     # kg, Liters, Bags, Units
    current_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    reorder_level = db.Column(db.Numeric(12, 2), nullable=False, default=10.00)
    storage_location = db.Column(db.String(100), nullable=True) # e.g. "Main Shed Bay 3"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    transactions = db.relationship("StockTransaction", backref="item", cascade="all, delete-orphan", lazy="dynamic")

    @property
    def is_low_stock(self) -> bool:
        return float(self.current_balance or 0) <= float(self.reorder_level or 0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "current_balance": float(self.current_balance),
            "reorder_level": float(self.reorder_level),
            "storage_location": self.storage_location,
            "is_low_stock": self.is_low_stock,
        }

    def __repr__(self):
        return f"<InventoryItem {self.name} ({self.current_balance} {self.unit})>"


class StockTransaction(db.Model):
    __tablename__ = "stock_transactions"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False) # IN (Purchase/Restock), OUT (Field Use), ADJUST
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    reference = db.Column(db.String(150), nullable=True) # Invoice #, Batch, Task ID, Field Block
    authorized_by = db.Column(db.String(100), nullable=False) # Manager / User
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_name": self.item.name if self.item else None,
            "type": self.type,
            "quantity": float(self.quantity),
            "date": self.date.isoformat() if self.date else None,
            "reference": self.reference,
            "authorized_by": self.authorized_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<StockTransaction {self.type} {self.quantity} for Item {self.item_id}>"
