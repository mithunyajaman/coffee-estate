"""Seed data script for AI-Powered Smart Coffee Estate Management System.

Populates:
1. Admin, Manager, and Employee accounts
2. Estate Blocks & Agronomic Activities
3. Harvest Records
4. Field Tasks
5. Inventory Items & Initial Stock Transactions
"""

from datetime import date, timedelta
from app import create_app
from app.database import db
from app.models.user import User
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.models.farm import EstateBlock, FarmActivity
from app.models.harvest import HarvestRecord
from app.models.task import Task
from app.models.inventory import InventoryItem, StockTransaction

def seed_database():
    app = create_app()
    with app.app_context():
        db.create_all()

        print("[Seed] Seeding Stage 1 & Stage 2 Records...")

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
            {
                "employee_code": "EMP002",
                "name": "Basavaraj Naik",
                "contact": "+91-9845045678",
                "email": "basavaraj@coffee-estate.local",
                "job_role": "Canopy Pruning Specialist",
                "wage_rate": 620.00,
                "status": "Active",
                "joining_date": date(2023, 2, 1),
            },
        ]

        for edata in employees_data:
            existing_emp = Employee.query.filter_by(employee_code=edata["employee_code"]).first()
            if not existing_emp:
                emp = Employee(**edata)
                db.session.add(emp)
                print(f"  + Added Employee: {edata['employee_code']} - {edata['name']}")

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
                print(f"  + Added User: {udata['username']} [{udata['role']}]")

        db.session.commit()

        # 3. Estate Blocks
        blocks_data = [
            {
                "name": "Block A - Arabica North Ridge",
                "area": 12.50,
                "unit": "Hectares",
                "variety": "Arabica Chandragiri",
                "location": "North Ridge, 1,180m ASL",
                "planting_date": date(2018, 7, 10),
                "status": "Active",
            },
            {
                "name": "Block B - Robusta Central Valley",
                "area": 18.00,
                "unit": "Hectares",
                "variety": "Robusta CxR",
                "location": "Central Valley, 1,020m ASL",
                "planting_date": date(2016, 8, 20),
                "status": "Active",
            },
            {
                "name": "Block C - Shade Nursery & Micro-Lot",
                "area": 6.20,
                "unit": "Hectares",
                "variety": "Arabica S.795 Selection",
                "location": "East Stream Bank, 1,140m ASL",
                "planting_date": date(2021, 9, 15),
                "status": "Active",
            },
            {
                "name": "Block D - South Terraces",
                "area": 9.80,
                "unit": "Hectares",
                "variety": "Arabica SLN-9",
                "location": "South Slope Terraces, 1,220m ASL",
                "planting_date": date(2019, 6, 5),
                "status": "Maintenance",
            },
        ]

        for bdata in blocks_data:
            existing_block = EstateBlock.query.filter_by(name=bdata["name"]).first()
            if not existing_block:
                b = EstateBlock(**bdata)
                db.session.add(b)
                print(f"  + Added Estate Block: {bdata['name']}")

        db.session.commit()

        # 4. Farm Activities
        block_a = EstateBlock.query.filter_by(name="Block A - Arabica North Ridge").first()
        block_b = EstateBlock.query.filter_by(name="Block B - Robusta Central Valley").first()
        if block_a and FarmActivity.query.count() == 0:
            acts = [
                FarmActivity(
                    block_id=block_a.id,
                    activity_type="Fertilizer Application",
                    date=date.today() - timedelta(days=5),
                    input_quantity="120 kg Complex 17-17-17",
                    notes="Applied pre-blossom shower booster across upper terraces.",
                    responsible_user="Deepak Kulkarni",
                ),
                FarmActivity(
                    block_id=block_a.id,
                    activity_type="Canopy Pruning",
                    date=date.today() - timedelta(days=2),
                    input_quantity="Manual shears",
                    notes="Centered desuckering and deadwood thinning.",
                    responsible_user="Deepak Kulkarni",
                ),
            ]
            if block_b:
                acts.append(
                    FarmActivity(
                        block_id=block_b.id,
                        activity_type="Drip Irrigation",
                        date=date.today() - timedelta(days=1),
                        input_quantity="4,500 L Drip",
                        notes="Supplemental drip irrigation following dry spell.",
                        responsible_user="Deepak Kulkarni",
                    )
                )
            db.session.add_all(acts)
            db.session.commit()
            print("  + Added sample FarmActivities.")

        # 5. Harvest Records
        if block_a and HarvestRecord.query.count() == 0:
            harvests = [
                HarvestRecord(
                    block_id=block_a.id,
                    date=date.today() - timedelta(days=4),
                    planned_quantity=500.0,
                    actual_quantity=520.5,
                    unit="kg",
                    team_id="North Ridge Pickers Gang A",
                    processing_status="Wet Pulped",
                    notes="High brix sugar reading (22°Bx). Ripe crimson cherries.",
                ),
                HarvestRecord(
                    block_id=block_a.id,
                    date=date.today() - timedelta(days=2),
                    planned_quantity=450.0,
                    actual_quantity=440.0,
                    unit="kg",
                    team_id="North Ridge Pickers Gang B",
                    processing_status="Raw Cherry",
                    notes="Selective hand-picking pass #2.",
                ),
            ]
            if block_b:
                harvests.append(
                    HarvestRecord(
                        block_id=block_b.id,
                        date=date.today() - timedelta(days=1),
                        planned_quantity=600.0,
                        actual_quantity=645.0,
                        unit="kg",
                        team_id="Central Gang 1",
                        processing_status="Dry Natural",
                        notes="Evenly spread across patio yard #3.",
                    )
                )
            db.session.add_all(harvests)
            db.session.commit()
            print("  + Added sample HarvestRecords.")

        # 6. Tasks
        emp1 = Employee.query.filter_by(employee_code="EMP001").first()
        emp2 = Employee.query.filter_by(employee_code="EMP002").first()
        if Task.query.count() == 0 and block_a:
            tasks = [
                Task(
                    title="Selective Picking on Block A Upper Rows",
                    instructions="Pick only dark crimson ripe cherries. Avoid stripping green berries.",
                    block_id=block_a.id,
                    assigned_to_id=emp1.id if emp1 else None,
                    start_date=date.today(),
                    due_date=date.today() + timedelta(days=2),
                    priority="High",
                    status="In Progress",
                ),
                Task(
                    title="Shade Lopping & Desuckering on Block B",
                    instructions="Trim excess silver oak branches to ensure 50-60% dappled sunlight.",
                    block_id=block_b.id if block_b else None,
                    assigned_to_id=emp2.id if emp2 else None,
                    start_date=date.today(),
                    due_date=date.today() + timedelta(days=4),
                    priority="Medium",
                    status="Pending",
                ),
            ]
            db.session.add_all(tasks)
            db.session.commit()
            print("  + Added sample Tasks.")

        # 7. Inventory Items & Stock Transactions
        if InventoryItem.query.count() == 0:
            items_data = [
                {
                    "name": "NPK 17-17-17 Complex Fertilizer",
                    "category": "Fertilizers",
                    "unit": "kg",
                    "current_balance": 1200.0,
                    "reorder_level": 300.0,
                    "storage_location": "Main Shed Bay 1",
                },
                {
                    "name": "Bordeaux Mixture 1% (Copper Sulfate)",
                    "category": "Crop Protection",
                    "unit": "kg",
                    "current_balance": 85.0,
                    "reorder_level": 100.0, # Intentional low-stock item for alert test!
                    "storage_location": "Chemical Lockup Room",
                },
                {
                    "name": "Food-Grade Jute Gunny Bags (60kg)",
                    "category": "Processing Supplies",
                    "unit": "Units",
                    "current_balance": 450.0,
                    "reorder_level": 100.0,
                    "storage_location": "Pulper Shed Bay 2",
                },
                {
                    "name": "High-Grade Diesel Fuel",
                    "category": "Fuel & Oil",
                    "unit": "Liters",
                    "current_balance": 600.0,
                    "reorder_level": 150.0,
                    "storage_location": "Fuel Tank #1",
                },
            ]
            for idata in items_data:
                it = InventoryItem(**idata)
                db.session.add(it)
                db.session.flush()

                # Add initial stock transaction
                tx = StockTransaction(
                    item_id=it.id,
                    type="IN",
                    quantity=it.current_balance,
                    date=date.today() - timedelta(days=10),
                    reference="Initial Estate Setup Receipt",
                    authorized_by="Vikram Gowda",
                )
                db.session.add(tx)

            db.session.commit()
            print("  + Added sample InventoryItems and initial stock ledger.")

        print("[Seed] All records seeded successfully.")

if __name__ == "__main__":
    seed_database()
