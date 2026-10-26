import csv
import io
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, jsonify
from app.database import db
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit
from app.models.farm import EstateBlock
from app.models.inventory import InventoryItem, StockTransaction
from app.models.pesticide import PesticideApplication

pesticides_bp = Blueprint("pesticides", __name__, url_prefix="/pesticides")


@pesticides_bp.route("/", methods=["GET"])
@login_required
def index():
    user = get_current_user()
    blocks = EstateBlock.query.filter_by(status="Active").order_by(EstateBlock.name.asc()).all()
    inventory_items = (
        InventoryItem.query.filter(
            InventoryItem.category.in_(["Crop Protection", "Fertilizer", "Bio-inputs", "Chemicals"])
        )
        .order_by(InventoryItem.name.asc())
        .all()
    )

    # Filter arguments
    selected_block = request.args.get("block_id", "")
    selected_category = request.args.get("category", "")
    selected_pest = request.args.get("target_pest", "")

    query = PesticideApplication.query
    if selected_block:
        query = query.filter(PesticideApplication.block_id == int(selected_block))
    if selected_category:
        query = query.filter(PesticideApplication.category == selected_category)
    if selected_pest:
        query = query.filter(PesticideApplication.target_pest.ilike(f"%{selected_pest}%"))

    applications = query.order_by(PesticideApplication.date.desc(), PesticideApplication.id.desc()).all()

    # Calculations for summary metrics
    today = date.today()
    active_phi_count = sum(1 for app in applications if app.is_within_phi)
    total_qty_applied = sum(float(app.quantity_used) for app in applications)
    total_bags_applied = sum(int(app.bags_count or 0) for app in applications)
    total_weight_kg_applied = sum(float(app.computed_weight_kg) for app in applications)
    total_employees_deployed = sum(int(app.total_employees_used or 1) for app in applications)

    # Find most prevalent target pest
    pest_counts = {}
    for app in applications:
        pest_counts[app.target_pest] = pest_counts.get(app.target_pest, 0) + 1
    top_pest = max(pest_counts, key=pest_counts.get) if pest_counts else "None"

    summary = {
        "total_applications": len(applications),
        "active_quarantine_blocks": active_phi_count,
        "total_qty_applied": round(total_qty_applied, 1),
        "total_bags_applied": total_bags_applied,
        "total_weight_kg_applied": round(total_weight_kg_applied, 1),
        "total_employees_deployed": total_employees_deployed,
        "top_pest": top_pest,
    }

    return render_template(
        "pesticides.html",
        applications=applications,
        blocks=blocks,
        inventory_items=inventory_items,
        summary=summary,
        selected_block=selected_block,
        selected_category=selected_category,
        selected_pest=selected_pest,
        today=today.isoformat(),
        is_manager=user.is_manager,
    )


@pesticides_bp.route("/add", methods=["POST"])
@login_required
@roles_required("Admin", "Estate Manager")
def add_application():
    user = get_current_user()
    block_id_raw = request.form.get("block_id")
    pesticide_name = request.form.get("pesticide_name", "").strip()
    category = request.form.get("category", "Fungicide").strip()
    target_pest = request.form.get("target_pest", "").strip()
    dosage = request.form.get("dosage", "").strip()
    qty_raw = request.form.get("quantity_used")
    unit = request.form.get("unit", "kg").strip()
    bags_count_raw = request.form.get("bags_count")
    bag_weight_kg_raw = request.form.get("bag_weight_kg")
    total_weight_kg_raw = request.form.get("total_weight_kg")
    app_date_raw = request.form.get("date")
    app_method = request.form.get("application_method", "Knapsack Sprayer").strip()
    phi_days = int(request.form.get("pre_harvest_interval_days") or 14)
    rei_hours = int(request.form.get("re_entry_interval_hours") or 24)
    weather = request.form.get("weather_condition", "Clear & Dry").strip()
    ppe = request.form.get("safety_ppe", "").strip()
    operator_name = request.form.get("operator_name", "").strip()
    total_employees_raw = request.form.get("total_employees_used")
    notes = request.form.get("notes", "").strip()
    inventory_item_id = request.form.get("inventory_item_id")

    # Parse workforce / employee count deployed
    try:
        total_employees_used = max(1, int(total_employees_raw)) if total_employees_raw else 1
    except ValueError:
        total_employees_used = 1

    # Parse bags and weight in kg
    bags_count = int(bags_count_raw) if bags_count_raw and bags_count_raw.isdigit() else 1
    try:
        bag_weight_kg = float(bag_weight_kg_raw) if bag_weight_kg_raw else 0.0
    except ValueError:
        bag_weight_kg = 0.0

    try:
        total_weight_kg = float(total_weight_kg_raw) if total_weight_kg_raw else 0.0
    except ValueError:
        total_weight_kg = 0.0

    # Auto calculate total weight if not directly passed but bags & bag weight given
    if total_weight_kg <= 0 and bags_count and bag_weight_kg > 0:
        total_weight_kg = round(bags_count * bag_weight_kg, 2)

    # If quantity was not provided directly, default to total weight or bags count
    if not qty_raw:
        if total_weight_kg > 0:
            qty_raw = str(total_weight_kg)
        else:
            qty_raw = str(bags_count)

    if not block_id_raw or not pesticide_name or not target_pest or not dosage or not qty_raw:
        flash("Block, Pesticide Name, Target Pest, Dosage, and Quantity/Bags are required.", "danger")
        return redirect(url_for("pesticides.index"))

    try:
        qty_val = float(qty_raw)
        if qty_val <= 0:
            raise ValueError
    except ValueError:
        flash("Quantity must be a positive number.", "danger")
        return redirect(url_for("pesticides.index"))

    # If total weight still 0 and unit is kg, adopt qty_val
    if total_weight_kg <= 0 and unit.lower() == "kg":
        total_weight_kg = qty_val
        if bags_count >= 1 and bag_weight_kg <= 0:
            bag_weight_kg = round(total_weight_kg / bags_count, 2)

    app_date = date.today()
    if app_date_raw:
        try:
            app_date = datetime.strptime(app_date_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    inv_id = int(inventory_item_id) if inventory_item_id and inventory_item_id.isdigit() else None

    # Create application record
    record = PesticideApplication(
        block_id=int(block_id_raw),
        date=app_date,
        pesticide_name=pesticide_name,
        category=category,
        target_pest=target_pest,
        dosage=dosage,
        quantity_used=qty_val,
        unit=unit,
        bags_count=bags_count,
        bag_weight_kg=bag_weight_kg,
        total_weight_kg=total_weight_kg,
        total_employees_used=total_employees_used,
        application_method=app_method,
        pre_harvest_interval_days=phi_days,
        re_entry_interval_hours=rei_hours,
        weather_condition=weather,
        safety_ppe=ppe or "Respirator, rubber gloves, apron",
        inventory_item_id=inv_id,
        operator_name=operator_name or user.username,
        supervised_by=user.username,
        notes=notes,
    )
    db.session.add(record)
    db.session.flush()

    # If linked to inventory store, deduct stock automatically
    if inv_id:
        item = db.session.get(InventoryItem, inv_id)
        if item:
            item.current_balance = max(0.0, float(item.current_balance or 0.0) - qty_val)
            tx = StockTransaction(
                item_id=item.id,
                type="OUT",
                quantity=qty_val,
                date=app_date,
                reference=f"Pesticide: {record.pesticide_name} ({target_pest}) on {record.block.name if record.block else block_id_raw}",
                authorized_by=user.username,
            )
            db.session.add(tx)

    db.session.commit()

    log_audit(
        action="PESTICIDE_APPLICATION_LOGGED",
        entity_type="PesticideApplication",
        entity_id=str(record.id),
        outcome="SUCCESS",
        details=f"Applied {pesticide_name} ({qty_val} {unit}, {bags_count} bags, {total_weight_kg} kg) on Block #{block_id_raw} on {app_date} using {total_employees_used} employees for {target_pest}. PHI: {phi_days} days.",
        actor_id=user.id,
        actor_username=user.username,
    )

    flash(
        f"Pesticide application logged successfully for {record.block.name if record.block else 'plot'}. Pre-harvest interval is {phi_days} days (Harvest permitted after {record.safe_harvest_date.strftime('%d-%b-%Y')}).",
        "success",
    )
    return redirect(url_for("pesticides.index"))


@pesticides_bp.route("/delete/<int:record_id>", methods=["POST"])
@login_required
@roles_required("Admin", "Estate Manager")
def delete_application(record_id):
    user = get_current_user()
    record = db.get_or_404(PesticideApplication, record_id)
    block_name = record.block.name if record.block else f"Block {record.block_id}"
    p_name = record.pesticide_name

    db.session.delete(record)
    db.session.commit()

    log_audit(
        action="PESTICIDE_RECORD_DELETED",
        entity_type="PesticideApplication",
        entity_id=str(record_id),
        outcome="SUCCESS",
        details=f"Deleted spraying record ID #{record_id} ({p_name} on {block_name})",
        actor_id=user.id,
        actor_username=user.username,
    )
    flash(f"Spraying record for {p_name} on {block_name} removed.", "info")
    return redirect(url_for("pesticides.index"))


@pesticides_bp.route("/export/csv", methods=["GET"])
@login_required
def export_csv():
    user = get_current_user()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Record ID", "Date Applied", "Block Name", "Pesticide Name", "Category", "Target Pest/Disease",
        "Dosage", "Quantity Applied", "Unit", "Number of Bags", "Weight per Bag (kg)", "Total Weight (kg)",
        "Total Employees Used", "Application Method", "Pre-Harvest Interval (Days)",
        "Safe Harvest Date", "Quarantine Status", "Re-entry (Hours)", "Weather", "Operator / Gang Lead", "Supervisor", "Notes"
    ])

    records = PesticideApplication.query.order_by(PesticideApplication.date.asc(), PesticideApplication.id.asc()).all()
    for r in records:
        writer.writerow([
            r.id,
            r.date.isoformat(),
            r.block.name if r.block else "",
            r.pesticide_name,
            r.category,
            r.target_pest,
            r.dosage,
            float(r.quantity_used),
            r.unit,
            r.bags_count or 1,
            float(r.bag_weight_kg or 0.0),
            float(r.computed_weight_kg),
            r.total_employees_used or 1,
            r.application_method,
            r.pre_harvest_interval_days,
            r.safe_harvest_date.isoformat(),
            f"Active Quarantine ({r.phi_remaining_days}d left)" if r.is_within_phi else "Safe to Harvest",
            r.re_entry_interval_hours,
            r.weather_condition or "",
            r.operator_name or "",
            r.supervised_by or "",
            r.notes or "",
        ])

    log_audit(
        action="PESTICIDE_REGISTER_CSV_EXPORT",
        entity_type="PesticideApplication",
        entity_id=None,
        outcome="SUCCESS",
        details="Exported official chemical spraying register in CSV format",
        actor_id=user.id,
        actor_username=user.username,
    )

    output.seek(0)
    filename = f"coffee_estate_pesticide_register_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
