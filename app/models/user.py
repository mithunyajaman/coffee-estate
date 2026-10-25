from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="Employee")  # Admin, Estate Manager, Employee
    status = db.Column(db.String(20), nullable=False, default="Active")  # Active, Inactive, Suspended
    employee_code = db.Column(db.String(50), nullable=True, index=True)  # Links to employee if applicable
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "Admin"

    @property
    def is_manager(self) -> bool:
        return self.role in ("Admin", "Estate Manager")

    @property
    def is_employee(self) -> bool:
        return self.role == "Employee"

    @property
    def is_active(self) -> bool:
        return self.status == "Active"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "employee_code": self.employee_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
