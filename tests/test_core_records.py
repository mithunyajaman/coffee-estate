from decimal import Decimal
from datetime import date
from app.database import db
from app.models.farm import EstateBlock, FarmActivity
from app.models.harvest import HarvestRecord
from app.models.employee import Employee
from app.models.task import Task
from app.models.inventory import InventoryItem, StockTransaction
from app.models.audit import AuditLog

# ==========================================
# 1. Farm Management Tests (Page 4)
# ==========================================

def test_view_farm_blocks(client, auth_client):
    """Authenticated users can view farm blocks."""
    auth_client.login_employee()
    resp = client.get("/farm")
    assert resp.status_code == 200
    assert b"Plantation Farm Management" in resp.data

def test_add_block_manager_allowed(client, auth_client):
    """Estate Manager can add a new block with audit logging."""
    auth_client.login_manager()
    resp = client.post("/farm/block/add", data={
        "name": "Block Test - High Peak",
        "area": "15.75",
        "unit": "Hectares",
        "variety": "Arabica Chandragiri",
        "location": "Upper Ridge",
        "status": "Active"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Block Test - High Peak" in resp.data

    block = EstateBlock.query.filter_by(name="Block Test - High Peak").first()
    assert block is not None
    assert block.area == Decimal("15.75")

    audit = AuditLog.query.filter_by(action="BLOCK_CREATE", entity_id=str(block.id)).first()
    assert audit is not None
    assert audit.outcome == "SUCCESS"

def test_add_block_validation_negative_area(client, auth_client):
    """Validation rejects negative or zero area."""
    auth_client.login_manager()
    resp = client.post("/farm/block/add", data={
        "name": "Invalid Area Block",
        "area": "-5.0",
        "variety": "Robusta",
    }, follow_redirects=True)
    assert b"Area must be a positive number" in resp.data

def test_log_field_activity(client, auth_client):
    """Manager can log agronomic activity on block."""
    auth_client.login_manager()
    block = EstateBlock(name="Activity Test Block", area=Decimal("5.0"), variety="SLN-9")
    db.session.add(block)
    db.session.commit()

    resp = client.post("/farm/activity/add", data={
        "block_id": block.id,
        "activity_type": "Drip Irrigation",
        "date": "2026-10-25",
        "input_quantity": "1000L",
        "notes": "Testing activity log"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Drip Irrigation" in resp.data

    act = FarmActivity.query.filter_by(block_id=block.id, activity_type="Drip Irrigation").first()
    assert act is not None
    assert act.input_quantity == "1000L"


# ==========================================
# 2. Harvest Management Tests (Page 8)
# ==========================================

def test_add_harvest_valid(client, auth_client):
    """Manager records harvest batch and calculates variance."""
    auth_client.login_manager()
    block = EstateBlock(name="H Block A", area=Decimal("4.5"), variety="Arabica")
    db.session.add(block)
    db.session.commit()

    resp = client.post("/harvest/add", data={
        "block_id": block.id,
        "date": "2026-10-25",
        "planned_quantity": "400.0",
        "actual_quantity": "450.5",
        "team_id": "Gang 1",
        "processing_status": "Raw Cherry",
        "notes": "Ripe cherries"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"450.5" in resp.data

    rec = HarvestRecord.query.filter_by(block_id=block.id, actual_quantity=Decimal("450.5")).first()
    assert rec is not None
    assert rec.variance_kg == 50.5

def test_harvest_negative_quantity_rejected(client, auth_client):
    """Rule: Harvest quantities cannot be negative."""
    auth_client.login_manager()
    block = EstateBlock(name="H Block B", area=Decimal("3.0"), variety="Robusta")
    db.session.add(block)
    db.session.commit()

    resp = client.post("/harvest/add", data={
        "block_id": block.id,
        "actual_quantity": "-100",
        "planned_quantity": "50",
    }, follow_redirects=True)
    assert b"Harvest quantities cannot be negative" in resp.data


# ==========================================
# 3. Employee Management Tests (Page 10)
# ==========================================

def test_employee_wage_restricted_for_regular_workers(client, auth_client):
    """Regular employee cannot see other employees' wage rates."""
    auth_client.login_employee()
    resp = client.get("/employees")
    assert resp.status_code == 200
    assert b"Restricted" in resp.data
    assert b"Register New Employee" not in resp.data

def test_employee_wage_visible_to_manager(client, auth_client):
    """Manager can view wage rates in clear text."""
    auth_client.login_manager()
    resp = client.get("/employees")
    assert resp.status_code == 200
    assert b"/ day" in resp.data
    assert b"Register Employee" in resp.data

def test_employee_cannot_add_worker(client, auth_client):
    """Regular worker is blocked by server-side RBAC from creating employees."""
    auth_client.login_employee()
    resp = client.post("/employees/add", data={
        "employee_code": "HACK01",
        "name": "Unauthorized Worker",
        "contact": "12345",
        "job_role": "Tester",
        "wage_rate": "9999"
    })
    assert resp.status_code == 403


# ==========================================
# 4. Task Management Tests (Page 14)
# ==========================================

def test_create_and_update_task(client, auth_client):
    """Manager creates task and assigned worker updates completion status."""
    auth_client.login_manager()
    emp = Employee.query.filter_by(employee_code="EMP001").first()
    assert emp is not None

    resp = client.post("/tasks/add", data={
        "title": "Weed Removal Row 1-10",
        "instructions": "Clear all creeper weeds",
        "assigned_to_id": emp.id,
        "priority": "High"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Weed Removal Row 1-10" in resp.data

    task = Task.query.filter_by(title="Weed Removal Row 1-10").first()
    assert task is not None
    assert task.status == "Pending"
    assert task.assigned_to_id == emp.id

    # Worker (EMP001) logs in and marks task Completed
    auth_client.login_employee()
    resp_up = client.post(f"/tasks/{task.id}/update-status", data={
        "status": "Completed",
        "completion_notes": "All 10 rows cleared."
    }, follow_redirects=True)
    assert resp_up.status_code == 200
    assert b"updated to" in resp_up.data and b"Completed" in resp_up.data

    db.session.refresh(task)
    assert task.status == "Completed"
    assert task.completion_notes == "All 10 rows cleared."


# ==========================================
# 5. Inventory & Negative Balance Tests (Page 17)
# ==========================================

def test_inventory_add_item_and_stock_in(client, auth_client):
    """Catalog item creation and Stock IN transaction."""
    auth_client.login_manager()
    resp = client.post("/inventory/item/add", data={
        "name": "Urea 46% Nitrogen",
        "category": "Fertilizers",
        "unit": "kg",
        "initial_quantity": "500",
        "reorder_level": "100"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Urea 46% Nitrogen" in resp.data

    item = InventoryItem.query.filter_by(name="Urea 46% Nitrogen").first()
    assert item is not None
    assert item.current_balance == Decimal("500")

def test_inventory_stock_out_success(client, auth_client):
    """Stock OUT within available balance succeeds and updates balance."""
    auth_client.login_manager()
    item = InventoryItem(
        name="Zinc Sulfate 21%",
        category="Fertilizers",
        unit="kg",
        current_balance=Decimal("200.00"),
        reorder_level=Decimal("50.00")
    )
    db.session.add(item)
    db.session.commit()

    resp = client.post("/inventory/transaction/add", data={
        "item_id": item.id,
        "type": "OUT",
        "quantity": "50",
        "reference": "Block A Foliar Application"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Stock OUT of 50" in resp.data

    db.session.refresh(item)
    assert item.current_balance == Decimal("150.00")

def test_inventory_rejects_negative_balance(client, auth_client):
    """Invariant Rule: Negative stock balances are strictly prevented."""
    auth_client.login_manager()
    item = InventoryItem(
        name="Copper Oxychloride 50%",
        category="Crop Protection",
        unit="kg",
        current_balance=Decimal("40.00"),
        reorder_level=Decimal("20.00")
    )
    db.session.add(item)
    db.session.commit()

    # Attempt to take OUT 100 kg when only 40 kg exists
    resp = client.post("/inventory/transaction/add", data={
        "item_id": item.id,
        "type": "OUT",
        "quantity": "100",
        "reference": "Overdrawing stock attempt"
    }, follow_redirects=True)
    assert b"Transaction Rejected: Insufficient balance" in resp.data
    assert b"Negative stock is not permitted" in resp.data

    db.session.refresh(item)
    # Balance must remain intact at 40
    assert item.current_balance == Decimal("40.00")
