from app.models.audit import AuditLog
from app.models.user import User

def test_loading_screen_accessible(client):
    """Page 1: Loading screen should be responsive and accessible."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"AI-Powered Smart Coffee Estate" in response.data
    assert b"Checking database connectivity" in response.data

def test_health_check_endpoint(client):
    """Health check endpoint returns healthy status and DB connectivity."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

def test_login_page_renders(client):
    """Page 2: Login page renders with expected fields."""
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Username or Employee ID" in response.data
    assert b"Password" in response.data

def test_successful_login_with_username(client, auth_client):
    """User can authenticate using username and receives role dashboard."""
    response = auth_client.login_admin()
    assert response.status_code == 200
    assert b"Estate Operations Dashboard" in response.data
    assert b"Admin View" in response.data

    # Verify audit log recorded
    log = AuditLog.query.filter_by(action="LOGIN_SUCCESS", actor_username="admin").first()
    assert log is not None
    assert log.outcome == "SUCCESS"

def test_successful_login_with_employee_code(client, auth_client):
    """User can authenticate using Employee ID (e.g. EMP001)."""
    response = auth_client.login("EMP001", "EmployeePassword@123")
    assert response.status_code == 200
    assert b"Employee View" in response.data

    log = AuditLog.query.filter_by(action="LOGIN_SUCCESS", actor_username="employee").first()
    assert log is not None

def test_invalid_password_rejected(client, auth_client):
    """Invalid credentials return 401 and safe message."""
    response = auth_client.login("admin", "WrongPassword!999")
    assert response.status_code == 401
    assert b"Invalid credentials" in response.data

    # Audit log recorded for failure
    log = AuditLog.query.filter_by(action="LOGIN_FAILURE").first()
    assert log is not None
    assert log.outcome == "FAILURE"

def test_nonexistent_user_rejected(client, auth_client):
    """Non-existent username returns 401 with safe error message."""
    response = auth_client.login("ghost_user", "AnyPassword")
    assert response.status_code == 401
    assert b"Invalid credentials" in response.data

def test_inactive_user_blocked(client, auth_client):
    """Suspended/inactive users are denied login."""
    response = auth_client.login("inactive_user", "InactivePassword@123")
    assert response.status_code == 403
    assert b"inactive or suspended" in response.data

def test_logout(client, auth_client):
    """Logout clears session and prevents dashboard access."""
    auth_client.login_employee()
    resp_dash = client.get("/dashboard")
    assert resp_dash.status_code == 200

    resp_logout = auth_client.logout()
    assert resp_logout.status_code == 200
    assert b"signed out safely" in resp_logout.data

    # Accessing dashboard after logout should redirect to login
    resp_dash_after = client.get("/dashboard")
    assert resp_dash_after.status_code == 302
    assert "/login" in resp_dash_after.headers["Location"]

def test_forgot_password_submission(client):
    """Forgot password logs request without account enumeration."""
    response = client.post("/forgot-password", data={"identifier": "admin"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"instructions to reset your password" in response.data

    log = AuditLog.query.filter_by(action="PASSWORD_RESET_REQUEST").first()
    assert log is not None


def test_face_login_api(client, app):
    """Tests Face Recognition login API endpoint."""
    resp = client.post("/api/auth/face-login", json={
        "simulate_employee_code": "EMP001"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "Ramesh Poojary" in data["message"]

    # Session should now be active
    resp_dash = client.get("/dashboard")
    assert resp_dash.status_code == 200


def test_new_user_registration(client, app):
    """Tests registration of new user and automatic employee account linking."""
    resp = client.post("/register", data={
        "name": "Priya Sharma",
        "username": "priya_sharma",
        "contact": "+91-9845099887",
        "email": "priya@coffee-estate.local",
        "role": "Employee",
        "password": "SecurePassword@123",
        "confirm_password": "SecurePassword@123",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Welcome to Emerald Heights Coffee Estate, Priya Sharma" in resp.data

    with app.app_context():
        from app.models.user import User
        from app.models.employee import Employee
        u = User.query.filter_by(username="priya_sharma").first()
        assert u is not None
        assert u.role == "Employee"
        emp = Employee.query.filter_by(employee_code=u.employee_code).first()
        assert emp is not None
        assert emp.name == "Priya Sharma"

