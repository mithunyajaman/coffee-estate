from app.models.audit import AuditLog

def test_unauthenticated_dashboard_redirect(client):
    """Anonymous user cannot access dashboard."""
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_admin_can_access_admin_api(client, auth_client):
    """Admin can access admin-only endpoints."""
    auth_client.login_admin()
    response = client.get("/api/admin/audit-logs")
    assert response.status_code == 200
    data = response.get_json()
    assert "logs" in data
    assert "total" in data

def test_employee_cannot_access_admin_api(client, auth_client):
    """Employee attempting to access Admin API receives 403 Forbidden."""
    auth_client.login_employee()
    response = client.get("/api/admin/audit-logs")
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "Forbidden"

    # Verify security audit was logged
    audit_event = AuditLog.query.filter_by(
        action="ROLE_ACCESS_DENIED",
        actor_username="employee"
    ).first()
    assert audit_event is not None
    assert audit_event.outcome == "DENIED"
    assert "api/admin/audit-logs" in audit_event.details

def test_manager_cannot_access_admin_api(client, auth_client):
    """Manager attempting to access Admin-only API receives 403 Forbidden."""
    auth_client.login_manager()
    response = client.get("/api/admin/audit-logs")
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "Forbidden"

def test_client_role_spoofing_ignored(client, auth_client):
    """Role spoofing via query params or headers cannot elevate privilege."""
    auth_client.login_employee()

    # Attempt with fake header and fake query parameter
    response = client.get(
        "/api/admin/audit-logs?role=Admin",
        headers={"X-User-Role": "Admin", "Role": "Admin"}
    )
    # Must still be strictly 403 Forbidden because server checks session user in DB
    assert response.status_code == 403
