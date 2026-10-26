from datetime import datetime, timezone, date
from app.database import db

class PayrollRecord(db.Model):
    """Monthly or period wage record calculated from verified attendance and rate cards."""
    __tablename__ = "payroll_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False, index=True)
    period_end = db.Column(db.Date, nullable=False, index=True)
    period_label = db.Column(db.String(60), nullable=False) # e.g. "October 2026"
    
    # Wage Rates & Attendance inputs
    daily_wage = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    payable_days = db.Column(db.Numeric(5, 2), nullable=False, default=0.00)
    present_days = db.Column(db.Integer, nullable=False, default=0)
    half_days = db.Column(db.Integer, nullable=False, default=0)
    absent_days = db.Column(db.Integer, nullable=False, default=0)
    
    # Overtime
    overtime_hours = db.Column(db.Numeric(5, 2), nullable=False, default=0.00)
    overtime_rate = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) # hourly overtime rate
    overtime_pay = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    
    # Gross & Deductions
    gross_pay = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    advances = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    deductions = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    net_pay = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    
    # Lifecycle & Approvals
    status = db.Column(db.String(30), nullable=False, default="Draft") # Draft, Approved, Disbursed, Cancelled
    payment_method = db.Column(db.String(30), nullable=False, default="Bank Transfer") # Bank Transfer, Cash, UPI
    payment_reference = db.Column(db.String(100), nullable=True)
    generated_by = db.Column(db.String(100), nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    disbursed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    employee = db.relationship("Employee", backref=db.backref("payroll_records", lazy=True, cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("employee_id", "period_start", "period_end", name="uq_emp_payroll_period"),
    )

    def calculate_totals(self):
        """Calculates Gross and Net Pay strictly according to the blueprint formula:
        Gross = (Payable Days * Daily Wage) + Approved Overtime
        Net = Gross - Advances - Deductions
        """
        days = float(self.payable_days or 0.0)
        wage = float(self.daily_wage or 0.0)
        ot = float(self.overtime_pay or 0.0)
        adv = float(self.advances or 0.0)
        ded = float(self.deductions or 0.0)

        calc_gross = (days * wage) + ot
        calc_net = calc_gross - adv - ded

        self.gross_pay = round(calc_gross, 2)
        self.net_pay = round(calc_net, 2)
        return self.gross_pay, self.net_pay

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_code": self.employee.employee_code if self.employee else None,
            "employee_name": self.employee.name if self.employee else None,
            "job_role": self.employee.job_role if self.employee else None,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_label": self.period_label,
            "daily_wage": float(self.daily_wage),
            "payable_days": float(self.payable_days),
            "present_days": self.present_days,
            "half_days": self.half_days,
            "absent_days": self.absent_days,
            "overtime_hours": float(self.overtime_hours),
            "overtime_rate": float(self.overtime_rate),
            "overtime_pay": float(self.overtime_pay),
            "gross_pay": float(self.gross_pay),
            "advances": float(self.advances),
            "deductions": float(self.deductions),
            "net_pay": float(self.net_pay),
            "status": self.status,
            "payment_method": self.payment_method,
            "payment_reference": self.payment_reference,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "notes": self.notes,
        }


class SalaryAdvance(db.Model):
    """Records wage advances requested or issued during the pay cycle."""
    __tablename__ = "salary_advances"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_record_id = db.Column(db.Integer, db.ForeignKey("payroll_records.id", ondelete="SET NULL"), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=date.today)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Approved") # Pending, Approved, Deducted, Cancelled
    approved_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    employee = db.relationship("Employee", backref=db.backref("salary_advances", lazy=True, cascade="all, delete-orphan"))
    payroll_record = db.relationship("PayrollRecord", backref=db.backref("advance_items", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.name if self.employee else None,
            "amount": float(self.amount),
            "request_date": self.request_date.isoformat() if self.request_date else None,
            "reason": self.reason,
            "status": self.status,
            "approved_by": self.approved_by,
        }
