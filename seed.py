"""Seed data script for AI-Powered Smart Coffee Estate Management System.

Populates:
1. One Admin User & Employee record
2. One Estate Manager User & Employee record
3. One Field Employee User & Employee record
"""

from datetime import date
from app import create_app
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.audit import AuditLog

def seed_database():
    app = create_app()
    with app.app_context():
        # Create all tables if not created yet
        db.create_all()

        print("[Seed] Checking existing records...")
        
        # 1. Employees Seed Data
        employees_data = [
            {
                "employee_code": "ADM001",
                "name": "Vikram Gowda",
                "contact": "+91-9845012345",
                "email": "admin@coffee-estate.local",
                "job_role": "Estate Director",
                "wage_rate": 2500.00,
                "status": "Active",
                "joining_date": date(2020, 1, 15),
            },
            {
                "employee_code": "MGR001",
                "name": "Deepak Kulkarni",
                "contact": "+91-9845023456",
                "email": "manager@coffee-estate.local",
                "job_role": "Senior Plantation Manager",
                "wage_rate": 1500.00,
                "status": "Active",
                "joining_date": date(2021, 6, 1),
            },
            {
                "employee_code": "EMP001",
                "name": "Ramesh Poojary",
                "contact": "+91-9845034567",
                "email": "employee@coffee-estate.local",
                "job_role": "Field Harvest Specialist",
                "wage_rate": 650.00,
                "status": "Active",
                "joining_date": date(2022, 10, 10),
            },
        ]

        for edata in employees_data:
            existing_emp = Employee.query.filter_by(employee_code=edata["employee_code"]).first()
            if not existing_emp:
                emp = Employee(**edata)
                db.session.add(emp)
                print(f"  + Added Employee: {edata['employee_code']} - {edata['name']}")
            else:
                print(f"  * Employee {edata['employee_code']} already exists")

        db.session.commit()

        # 2. Users Seed Data
        users_data = [
            {
                "username": "admin",
                "email": "admin@coffee-estate.local",
                "password": "AdminPassword@123",
                "role": "Admin",
                "employee_code": "ADM001",
                "status": "Active",
            },
            {
                "username": "manager",
                "email": "manager@coffee-estate.local",
                "password": "ManagerPassword@123",
                "role": "Estate Manager",
                "employee_code": "MGR001",
                "status": "Active",
            },
            {
                "username": "employee",
                "email": "employee@coffee-estate.local",
                "password": "EmployeePassword@123",
                "role": "Employee",
                "employee_code": "EMP001",
                "status": "Active",
            },
        ]

        for udata in users_data:
            existing_user = User.query.filter_by(username=udata["username"]).first()
            if not existing_user:
                u = User(
                    username=udata["username"],
                    email=udata["email"],
                    role=udata["role"],
                    employee_code=udata["employee_code"],
                    status=udata["status"],
                )
                u.set_password(udata["password"])
                db.session.add(u)
                print(f"  + Added User: {udata['username']} [{udata['role']}] (Password: {udata['password']})")
            else:
                print(f"  * User {udata['username']} already exists")

        db.session.commit()

        # 3. Initial Audit Log
        if AuditLog.query.count() == 0:
            init_audit = AuditLog(
                actor_id=1,
                actor_username="system_seeder",
                action="INITIAL_SEED",
                entity_type="System",
                entity_id="init",
                outcome="SUCCESS",
                details="Seeded initial Admin, Manager, and Employee credentials and employee profiles.",
            )
            db.session.add(init_audit)
            db.session.commit()
            print("  + Seeded initial AuditLog entry.")

        print("[Seed] Seeding completed successfully.")

if __name__ == "__main__":
    seed_database()
