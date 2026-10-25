from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func
from app.database import db
from app.models.farm import EstateBlock
from app.models.harvest import HarvestRecord
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

harvest_bp = Blueprint("harvest", __name__)

@harvest_bp.route("/harvest")
@login_required
def harvest_list():
    """Page 8: Harvest Management."""
    current_user = get_current_user()
    block_filter = request.args.get("block_id", type=int)
    status_filter = request.args.get("processing_status", "").strip()
    page = request.args.get("page", 1, type=int)

    query = HarvestRecord.query
    if block_filter:
        query = query.filter_by(block_id=block_filter)
    if status_filter:
        query = query.filter_by(processing_status=status_filter)

    pagination = query.order_by(HarvestRecord.date.desc(), HarvestRecord.id.desc()).paginate(page=page, per_page=10, error_out=False)
    records = pagination.items

    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()

    # Aggregate summaries
    total_harvest_kg = db.session.query(func.coalesce(func.sum(HarvestRecord.actual_quantity), 0)).scalar()
    total_planned_kg = db.session.query(func.coalesce(func.sum(HarvestRecord.planned_quantity), 0)).scalar()

    return render_template(
        "harvest.html",
        records=records,
        pagination=pagination,
        blocks=blocks,
        total_harvest_kg=float(total_harvest_kg),
        total_planned_kg=float(total_planned_kg),
        block_filter=block_filter,
        status_filter=status_filter,
        current_user=current_user,
    )


@harvest_bp.route("/harvest/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_harvest():
    """Record daily harvest batch."""
    current_user = get_current_user()
    block_id = request.form.get("block_id", type=int)
    date_str = request.form.get("date") or str(date.today())
    planned_str = request.form.get("planned_quantity") or "0"
    actual_str = request.form.get("actual_quantity") or "0"
    team_id = (request.form.get("team_id") or "").strip()
    processing_status = request.form.get("processing_status") or "Raw Cherry"
    notes = (request.form.get("notes") or "").strip()

    block = db.session.get(EstateBlock, block_id)
    if not block:
        flash("Invalid estate block selected.", "danger")
        return redirect(url_for("harvest.harvest_list"))

    try:
        planned_qty = Decimal(planned_str)
        actual_qty = Decimal(actual_str)
        # Validation: prevent invalid negative quantities
        if planned_qty < 0 or actual_qty < 0:
            flash("Harvest quantities cannot be negative.", "danger")
            return redirect(url_for("harvest.harvest_list"))
    except Exception:
        flash("Invalid harvest numerical quantities.", "danger")
        return redirect(url_for("harvest.harvest_list"))

    try:
        rec_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        rec_date = date.today()

    record = HarvestRecord(
        block_id=block.id,
        date=rec_date,
        planned_quantity=planned_qty,
        actual_quantity=actual_qty,
        unit="kg",
        team_id=team_id,
        processing_status=processing_status,
        notes=notes,
    )
    db.session.add(record)
    db.session.commit()

    log_audit(
        action="HARVEST_RECORD_CREATE",
        entity_type="HarvestRecord",
        entity_id=str(record.id),
        outcome="SUCCESS",
        details=f"Recorded {actual_qty} kg harvest for {block.name} (Planned: {planned_qty} kg, Status: {processing_status})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Harvest of {actual_qty} kg recorded for {block.name}.", "success")
    return redirect(url_for("harvest.harvest_list"))


@harvest_bp.route("/harvest/<int:record_id>/delete", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def delete_harvest(record_id):
    """Delete a harvest record with audit tracking."""
    current_user = get_current_user()
    record = db.session.get(HarvestRecord, record_id)
    if not record:
        flash("Harvest record not found.", "danger")
        return redirect(url_for("harvest.harvest_list"))

    block_name = record.block.name if record.block else f"Block {record.block_id}"
    qty = record.actual_quantity

    db.session.delete(record)
    db.session.commit()

    log_audit(
        action="HARVEST_RECORD_DELETE",
        entity_type="HarvestRecord",
        entity_id=str(record_id),
        outcome="SUCCESS",
        details=f"Deleted harvest record of {qty} kg from {block_name}",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Harvest record #{record_id} deleted successfully.", "info")
    return redirect(url_for("harvest.harvest_list"))
