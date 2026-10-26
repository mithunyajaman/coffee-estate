from datetime import date, timedelta
from app.database import db
from app.models.farm import EstateBlock
from app.models.inventory import InventoryItem, StockTransaction
from app.models.pesticide import PesticideApplication

def test_pesticides_page_load(client, auth_client, app):
    """Verifies that Pesticides Register page loads with summary metrics."""
    auth_client.login_manager()
    resp = client.get("/pesticides/")
    assert resp.status_code == 200
    assert b"Pesticides &amp; Crop Protection Register" in resp.data
    assert b"Active Quarantine (PHI)" in resp.data
    assert b"Log Spraying Operation" in resp.data


def test_add_pesticide_application_and_inventory_deduction(client, auth_client, app):
    """Tests logging a spraying operation with automatic inventory store deduction."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Plot Test", area=4.5, unit="Hectares", variety="Arabica", location="Valley")
            db.session.add(block)

        item = InventoryItem(
            name="Hexaconazole 5% EC Fungicide",
            category="Crop Protection",
            unit="Liters",
            current_balance=50.0,
            reorder_level=10.0,
        )
        db.session.add(item)
        db.session.commit()
        block_id = block.id
        item_id = item.id

    auth_client.login_manager()

    resp = client.post("/pesticides/add", data={
        "block_id": str(block_id),
        "date": date.today().isoformat(),
        "pesticide_name": "Hexaconazole 5% EC Fungicide",
        "category": "Fungicide",
        "target_pest": "Coffee Leaf Rust",
        "dosage": "2 ml / Liter",
        "quantity_used": "10.0",
        "unit": "Liters",
        "application_method": "Knapsack Sprayer",
        "pre_harvest_interval_days": "15",
        "re_entry_interval_hours": "24",
        "weather_condition": "Sunny morning",
        "safety_ppe": "Respirator, gloves",
        "inventory_item_id": str(item_id),
        "operator_name": "Basavaraj Naik",
        "notes": "Covered lower canopy",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Pesticide application logged successfully" in resp.data

    with app.app_context():
        app_rec = PesticideApplication.query.filter_by(target_pest="Coffee Leaf Rust").first()
        assert app_rec is not None
        assert float(app_rec.quantity_used) == 10.0
        assert app_rec.pre_harvest_interval_days == 15
        assert app_rec.is_within_phi is True
        assert app_rec.phi_remaining_days == 15

        # Check inventory balance was deducted: 50.0 - 10.0 = 40.0
        inv = db.session.get(InventoryItem, item_id)
        assert float(inv.current_balance) == 40.0

        # Check StockTransaction OUT was logged
        tx = StockTransaction.query.filter_by(item_id=item_id, type="OUT").first()
        assert tx is not None
        assert float(tx.quantity) == 10.0


def test_pre_harvest_interval_logic(app):
    """Verifies that PHI quarantine countdown logic correctly calculates safe harvest dates."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Plot Test 2", area=3.0, unit="Hectares", variety="Robusta", location="Hill")
            db.session.add(block)
            db.session.commit()

        # Application 1: Today with 14 days PHI -> Active Quarantine
        app_active = PesticideApplication(
            block_id=block.id,
            date=date.today(),
            pesticide_name="Active Spray",
            category="Insecticide",
            target_pest="Berry Borer",
            dosage="1kg/200L",
            quantity_used=5.0,
            pre_harvest_interval_days=14,
        )

        # Application 2: 25 days ago with 10 days PHI -> Safe to harvest
        app_safe = PesticideApplication(
            block_id=block.id,
            date=date.today() - timedelta(days=25),
            pesticide_name="Old Spray",
            category="Bio-pesticide",
            target_pest="Mealybug",
            dosage="2L/200L",
            quantity_used=4.0,
            pre_harvest_interval_days=10,
        )
        db.session.add_all([app_active, app_safe])
        db.session.commit()

        assert app_active.is_within_phi is True
        assert app_active.phi_remaining_days == 14
        assert app_active.safe_harvest_date == date.today() + timedelta(days=14)

        assert app_safe.is_within_phi is False
        assert app_safe.phi_remaining_days == 0
        assert app_safe.safe_harvest_date == (date.today() - timedelta(days=25)) + timedelta(days=10)


def test_pesticides_export_csv(client, auth_client, app):
    """Tests CSV chemical register download."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="CSV Block", area=2.0, unit="Hectares", variety="Arabica", location="Slope")
            db.session.add(block)
            db.session.commit()

        db.session.add(PesticideApplication(
            block_id=block.id,
            date=date.today(),
            pesticide_name="Export Chemical Test",
            category="Fungicide",
            target_pest="Leaf Spot",
            dosage="500g/200L",
            quantity_used=6.0,
            unit="kg",
            pre_harvest_interval_days=12,
        ))
        db.session.commit()

    auth_client.login_manager()
    resp = client.get("/pesticides/export/csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"Date Applied" in resp.data
    assert b"Pesticide Name" in resp.data
    assert b"Number of Bags" in resp.data
    assert b"Weight per Bag (kg)" in resp.data
    assert b"Total Weight (kg)" in resp.data
    assert b"Total Employees Used" in resp.data
    assert b"Export Chemical Test" in resp.data
    assert b"Leaf Spot" in resp.data


def test_worker_cannot_add_or_delete_pesticide(client, auth_client, app):
    """Field Workers can view the register for safety awareness but cannot add or delete."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Guard Block", area=2.0, unit="Hectares", variety="Arabica", location="Slope")
            db.session.add(block)
            db.session.commit()

        p = PesticideApplication(
            block_id=block.id,
            date=date.today(),
            pesticide_name="Restricted Chemical",
            category="Insecticide",
            target_pest="Stem Borer",
            dosage="500ml",
            quantity_used=2.0,
        )
        db.session.add(p)
        db.session.commit()
        pid = p.id

    auth_client.login_employee()

    # Worker can view
    resp_view = client.get("/pesticides/")
    assert resp_view.status_code == 200

    # Worker cannot add -> 403 Forbidden
    resp_add = client.post("/pesticides/add", data={"pesticide_name": "Unauthorized"})
    assert resp_add.status_code == 403

    # Worker cannot delete -> 403 Forbidden
    resp_del = client.post(f"/pesticides/delete/{pid}")
    assert resp_del.status_code == 403


def test_pesticide_bags_and_weight_tracking(client, auth_client, app):
    """Verifies that pesticide bags count and weight in kg are correctly captured, computed, and displayed."""
    with app.app_context():
        block = EstateBlock.query.first()
        if not block:
            block = EstateBlock(name="Bags Block", area=5.0, unit="Hectares", variety="Arabica", location="Ridge")
            db.session.add(block)
            db.session.commit()
        block_id = block.id

    auth_client.login_manager()

    # Post an application with 4 bags of 25 kg each = 100 kg total and 3 employees
    resp = client.post("/pesticides/add", data={
        "block_id": str(block_id),
        "date": date.today().isoformat(),
        "pesticide_name": "Copper Sulfate Blue Crystals",
        "category": "Fungicide",
        "target_pest": "Coffee Black Rot",
        "dosage": "1 kg per 200L water",
        "bags_count": "4",
        "bag_weight_kg": "25.0",
        "total_weight_kg": "100.0",
        "total_employees_used": "3",
        "quantity_used": "100.0",
        "unit": "kg",
        "operator_name": "Suresh Gowda",
        "application_method": "Knapsack Sprayer",
        "pre_harvest_interval_days": "14",
        "re_entry_interval_hours": "24",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Pesticide application logged successfully" in resp.data

    with app.app_context():
        rec = PesticideApplication.query.filter_by(pesticide_name="Copper Sulfate Blue Crystals").first()
        assert rec is not None
        assert rec.bags_count == 4
        assert float(rec.bag_weight_kg) == 25.0
        assert float(rec.total_weight_kg) == 100.0
        assert float(rec.computed_weight_kg) == 100.0
        assert rec.total_employees_used == 3
        assert rec.date == date.today()

        d = rec.to_dict()
        assert d["bags_count"] == 4
        assert d["bag_weight_kg"] == 25.0
        assert d["total_weight_kg"] == 100.0
        assert d["total_employees_used"] == 3
        assert d["date_applied"] == date.today().isoformat()

    # Verify rendering on UI
    resp_ui = client.get("/pesticides/")
    assert resp_ui.status_code == 200
    assert b"4 Bags" in resp_ui.data
    assert b"100.0 kg" in resp_ui.data
    assert b"25.00 kg / bag" in resp_ui.data
    assert b"3 Workers" in resp_ui.data
    assert b"Copper Sulfate Blue Crystals" in resp_ui.data
