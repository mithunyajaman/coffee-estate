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
from app.models.attendance import DailyAttendance
from app.models.payroll import PayrollRecord, SalaryAdvance
from app.services.payroll_service import generate_payroll_record

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

        # 8. Attendance Records: Kept empty per user request ("data I will add, you don't add")
        print("[Seed] Attendance data will be entered by estate administrator/manager directly.")

        # 9. Seed Salary Advances and Sample Payroll
        print("[Seed] Seeding Stage 4 Payroll & Advances...")
        if emp1:
            existing_adv = SalaryAdvance.query.filter_by(employee_id=emp1.id).first()
            if not existing_adv:
                adv = SalaryAdvance(
                    employee_id=emp1.id,
                    amount=1500.00,
                    request_date=today - timedelta(days=5),
                    reason="Medical emergency & clinic visit",
                    status="Approved",
                    approved_by="Deepak Kulkarni",
                )
                db.session.add(adv)
                db.session.commit()

            start_period = today.replace(day=1)
            if today.month == 12:
                end_period = date(today.year, 12, 31)
            else:
                end_period = date.fromordinal(date(today.year, today.month + 1, 1).toordinal() - 1)
            
            p_record = generate_payroll_record(
                employee_id=emp1.id,
                start_date=start_period,
                end_date=end_period,
                period_label=today.strftime("%B %Y"),
                overtime_hours=8.0,
                overtime_rate=120.00,
                advances_amount=1500.00,
                deductions_amount=350.00,
                generated_by="manager",
                notes="Verified against biometric muster and supervisor log",
            )
            p_record.status = "Approved"
            p_record.approved_by = "Deepak Kulkarni"
            from datetime import datetime, timezone
            p_record.approved_at = datetime.now(timezone.utc)
            db.session.commit()
            print(f"  + Generated sample PayrollRecord: Net Pay = INR {p_record.net_pay}")

        # 10. Seed Face Biometric Profile for EMP001 (Ramesh Poojary)
        from app.models.attendance import FaceEnrollment
        import json
        if emp1:
            existing_face = FaceEnrollment.query.filter_by(employee_id=emp1.id).first()
            if not existing_face:
                sample_vector = [round(((i * 7 + 13) % 100) / 100.0 - 0.5, 4) for i in range(128)]
                v_mag = sum(x * x for x in sample_vector) ** 0.5
                norm_vector = [round(x / v_mag, 5) for x in sample_vector]
                
                face_enr = FaceEnrollment(
                    employee_id=emp1.id,
                    consent_status=True,
                    consent_timestamp=datetime.now(timezone.utc),
                    protected_template=json.dumps(norm_vector),
                    enrollment_status="Enrolled",
                    confidence_threshold=0.75,
                )
                db.session.add(face_enr)
                db.session.commit()
                print("  + Seeded Face Biometric Enrollment for Ramesh Poojary (EMP001)")

        # 11. Seed Pesticide Application Records
        from app.models.pesticide import PesticideApplication
        print("[Seed] Seeding Pesticide & Crop Protection records...")
        block_a = EstateBlock.query.filter_by(name="Block A - Arabica North Ridge").first()
        block_b = EstateBlock.query.filter_by(name="Block B - Robusta Central Valley").first()
        block_c = EstateBlock.query.filter_by(name="Block C - Shade Nursery & Micro-Lot").first()

        if block_a and not PesticideApplication.query.filter_by(block_id=block_a.id).first():
            p_item = InventoryItem.query.filter(InventoryItem.name.ilike("%Copper%")).first()
            inv_id = p_item.id if p_item else None

            # 1. Active quarantine on Block A (Leaf rust)
            p1 = PesticideApplication(
                block_id=block_a.id,
                date=today - timedelta(days=5),
                pesticide_name="Copper Oxychloride 50% WP (Bordeaux Mixture)",
                category="Fungicide",
                target_pest="Coffee Leaf Rust (Hemileia vastatrix)",
                dosage="500g per 200L water (0.25%)",
                quantity_used=25.0,
                unit="kg",
                bags_count=1,
                bag_weight_kg=25.0,
                total_weight_kg=25.0,
                total_employees_used=3,
                application_method="Knapsack Sprayer",
                pre_harvest_interval_days=14,
                re_entry_interval_hours=24,
                weather_condition="Clear sunrise, 22°C, 65% RH",
                safety_ppe="Respirator mask, goggles, nitrile gloves, chemical apron",
                inventory_item_id=inv_id,
                operator_name="Basavaraj Naik (Spraying Squad A)",
                supervised_by="Deepak Kulkarni",
                notes="Targeted upper & lower canopy foliage before southwest monsoon",
            )
            db.session.add(p1)

            # 2. Cleared quarantine on Block B (Berry borer)
            if block_b:
                p2 = PesticideApplication(
                    block_id=block_b.id,
                    date=today - timedelta(days=18),
                    pesticide_name="Beauveria bassiana 1.15% WP (Biopesticide)",
                    category="Bio-pesticide",
                    target_pest="Coffee Berry Borer (Hypothenemus hampei)",
                    dosage="1 kg per 200L water",
                    quantity_used=10.0,
                    unit="kg",
                    bags_count=2,
                    bag_weight_kg=5.0,
                    total_weight_kg=10.0,
                    total_employees_used=2,
                    application_method="Tractor Mist Blower",
                    pre_harvest_interval_days=7,
                    re_entry_interval_hours=12,
                    weather_condition="Overcast, High humidity (80% RH)",
                    safety_ppe="Standard mask & rubber gloves",
                    operator_name="Ramesh Poojary",
                    supervised_by="Deepak Kulkarni",
                    notes="Biological entomopathogenic fungus applied during green bean hardening stage",
                )
                db.session.add(p2)

            # 3. Active quarantine on Block C (Stem borer swab)
            if block_c:
                p3 = PesticideApplication(
                    block_id=block_c.id,
                    date=today - timedelta(days=2),
                    pesticide_name="Chlorpyrifos 20% EC + Lime Slurry",
                    category="Insecticide",
                    target_pest="White Stem Borer (Xylotrechus quadripes)",
                    dosage="500 ml / 200L water with 10% lime slurry",
                    quantity_used=25.0,
                    unit="kg",
                    bags_count=1,
                    bag_weight_kg=25.0,
                    total_weight_kg=25.0,
                    total_employees_used=4,
                    application_method="Stem Painting / Swabbing",
                    pre_harvest_interval_days=30,
                    re_entry_interval_hours=48,
                    weather_condition="Sunny, Dry morning",
                    safety_ppe="Full chemical PPE, face shield, heavy rubber gauntlets",
                    operator_name="Pruning & Swabbing Team",
                    supervised_by="Vikram Gowda",
                    notes="Applied to main trunk and thick primaries up to 1.2m height",
                )
                db.session.add(p3)

            db.session.commit()
            print("  + Seeded 3 Pesticide Application Records with PHI quarantine intervals.")

        print("[Seed] All records seeded successfully.")

if __name__ == "__main__":
    seed_database()
