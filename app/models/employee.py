from datetime import datetime, timezone, date
from app.database import db

class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    job_role = db.Column(db.String(80), nullable=False)  # e.g., Estate Worker, Field Supervisor, Pruning Specialist
    wage_rate = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # Daily wage
    status = db.Column(db.String(20), nullable=False, default="Active")  # Active, On Leave, Inactive
    joining_date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self, include_wage: bool = True):
        data = {
            "id": self.id,
            "employee_code": self.employee_code,
            "name": self.name,
            "contact": self.contact,
            "email": self.email,
            "job_role": self.job_role,
            "status": self.status,
            "joining_date": self.joining_date.isoformat() if self.joining_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_wage:
            data["wage_rate"] = float(self.wage_rate) if self.wage_rate is not None else 0.0
        return data

    def __repr__(self):
        return f"<Employee {self.employee_code} - {self.name}>"
