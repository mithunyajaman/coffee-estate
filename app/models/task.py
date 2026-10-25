from datetime import datetime, timezone, date
from app.database import db

class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    block_id = db.Column(db.Integer, db.ForeignKey("estate_blocks.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="Medium") # High, Medium, Low
    status = db.Column(db.String(30), nullable=False, default="Pending") # Pending, In Progress, Completed, Cancelled
    completion_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    assigned_employee = db.relationship("Employee", backref="assigned_tasks")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "instructions": self.instructions,
            "block_id": self.block_id,
            "block_name": self.block.name if self.block else None,
            "assigned_to_id": self.assigned_to_id,
            "assigned_to_name": self.assigned_employee.name if self.assigned_employee else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority,
            "status": self.status,
            "completion_notes": self.completion_notes,
        }

    def __repr__(self):
        return f"<Task {self.title} [{self.status}]>"
