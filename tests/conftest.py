import pytest
from datetime import date
from app import create_app
from app.config import TestingConfig
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.audit import AuditLog

@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()

        # Seed test employees
        emp_adm = Employee(
            employee_code="ADM001",
            name="Vikram Gowda",
            contact="+91-9845012345",
            email="admin@coffee-estate.local",
            job_role="Estate Director",
            wage_rate=2500.00,
            status="Active",
            joining_date=date(2020, 1, 15),
        )
        emp_mgr = Employee(
            employee_code="MGR001",
            name="Deepak Kulkarni",
            contact="+91-9845023456",
            email="manager@coffee-estate.local",
            job_role="Senior Plantation Manager",
            wage_rate=1500.00,
            status="Active",
            joining_date=date(2021, 6, 1),
        )
        emp_wrk = Employee(
            employee_code="EMP001",
            name="Ramesh Poojary",
            contact="+91-9845034567",
            email="employee@coffee-estate.local",
            job_role="Field Harvest Specialist",
            wage_rate=650.00,
            status="Active",
            joining_date=date(2022, 10, 10),
        )
        db.session.add_all([emp_adm, emp_mgr, emp_wrk])
        db.session.commit()

        # Seed test users
        u_admin = User(username="admin", email="admin@coffee-estate.local", role="Admin", employee_code="ADM001", status="Active")
        u_admin.set_password("AdminPassword@123")

        u_manager = User(username="manager", email="manager@coffee-estate.local", role="Estate Manager", employee_code="MGR001", status="Active")
        u_manager.set_password("ManagerPassword@123")

        u_emp = User(username="employee", email="employee@coffee-estate.local", role="Employee", employee_code="EMP001", status="Active")
        u_emp.set_password("EmployeePassword@123")

        u_inactive = User(username="inactive_user", email="inactive@coffee-estate.local", role="Employee", employee_code="EMP999", status="Inactive")
        u_inactive.set_password("InactivePassword@123")

        db.session.add_all([u_admin, u_manager, u_emp, u_inactive])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client):
    """Helper class for logging in with different roles during tests."""
    class AuthHelper:
        def login(self, identifier, password):
            return client.post("/login", data={
                "identifier": identifier,
                "password": password
            }, follow_redirects=True)

        def login_admin(self):
            return self.login("admin", "AdminPassword@123")

        def login_manager(self):
            return self.login("manager", "ManagerPassword@123")

        def login_employee(self):
            return self.login("employee", "EmployeePassword@123")

        def logout(self):
            return client.get("/logout", follow_redirects=True)

    return AuthHelper()
