from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.database import db
from app.models.farm import EstateBlock, FarmActivity
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

farm_bp = Blueprint("farm", __name__)

@farm_bp.route("/farm")
@login_required
def farm_list():
    """Page 4: Farm Management (Estate Blocks & Field Activities)."""
    current_user = get_current_user()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    variety_filter = request.args.get("variety", "").strip()
    page = request.args.get("page", 1, type=int)

    query = EstateBlock.query
    if search:
        query = query.filter(
            (EstateBlock.name.ilike(f"%{search}%")) |
            (EstateBlock.variety.ilike(f"%{search}%")) |
            (EstateBlock.location.ilike(f"%{search}%"))
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    if variety_filter:
        query = query.filter(EstateBlock.variety.ilike(f"%{variety_filter}%"))

    pagination = query.order_by(EstateBlock.name.asc()).paginate(page=page, per_page=12, error_out=False)
    blocks = pagination.items

    all_blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()
    arabica_count = sum(1 for b in all_blocks if "arabica" in (b.variety or "").lower())
    robusta_count = sum(1 for b in all_blocks if "robusta" in (b.variety or "").lower())
    kaveri_count = sum(1 for b in all_blocks if "kaveri" in (b.variety or "").lower() or "cauvery" in (b.variety or "").lower())

    arabica_hectares = sum(float(b.area or 0) for b in all_blocks if "arabica" in (b.variety or "").lower())
    robusta_hectares = sum(float(b.area or 0) for b in all_blocks if "robusta" in (b.variety or "").lower())
    kaveri_hectares = sum(float(b.area or 0) for b in all_blocks if "kaveri" in (b.variety or "").lower() or "cauvery" in (b.variety or "").lower())

    # Recent activities across the estate
    recent_activities = (
        FarmActivity.query.order_by(FarmActivity.date.desc(), FarmActivity.id.desc())
        .limit(10)
        .all()
    )

    total_hectares = sum([float(b.area or 0) for b in all_blocks])

    return render_template(
        "farm.html",
        blocks=blocks,
        all_blocks=all_blocks,
        pagination=pagination,
        recent_activities=recent_activities,
        total_hectares=total_hectares,
        search=search,
        status_filter=status_filter,
        variety_filter=variety_filter,
        arabica_count=arabica_count,
        robusta_count=robusta_count,
        kaveri_count=kaveri_count,
        arabica_hectares=arabica_hectares,
        robusta_hectares=robusta_hectares,
        kaveri_hectares=kaveri_hectares,
        date_today=date.today().isoformat(),
        current_user=current_user,
    )


@farm_bp.route("/farm/block/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_block():
    """Create a new plantation block."""
    current_user = get_current_user()
    name = (request.form.get("name") or "").strip()
    area_str = request.form.get("area") or "0"
    unit = request.form.get("unit") or "Hectares"
    variety = (request.form.get("variety") or "").strip()
    location = (request.form.get("location") or "").strip()
    planting_date_str = request.form.get("planting_date") or None
    status = request.form.get("status") or "Active"

    if not name or not variety:
        flash("Block name and coffee variety are required.", "danger")
        return redirect(url_for("farm.farm_list"))

    try:
        area = Decimal(area_str)
        if area <= 0:
            flash("Area must be a positive number.", "danger")
            return redirect(url_for("farm.farm_list"))
    except Exception:
        flash("Invalid area numerical value.", "danger")
        return redirect(url_for("farm.farm_list"))

    planting_date = None
    if planting_date_str:
        try:
            planting_date = datetime.strptime(planting_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    existing = EstateBlock.query.filter_by(name=name).first()
    if existing:
        flash(f"A block named '{name}' already exists.", "danger")
        return redirect(url_for("farm.farm_list"))

    block = EstateBlock(
        name=name,
        area=area,
        unit=unit,
        variety=variety,
        location=location,
        planting_date=planting_date,
        status=status,
    )
    db.session.add(block)
    db.session.commit()

    log_audit(
        action="BLOCK_CREATE",
        entity_type="EstateBlock",
        entity_id=str(block.id),
        outcome="SUCCESS",
        details=f"Created block '{block.name}' ({block.area} {block.unit}, {block.variety})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Plantation block '{block.name}' added successfully.", "success")
    return redirect(url_for("farm.farm_list"))


@farm_bp.route("/farm/block/<int:block_id>/edit", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def edit_block(block_id):
    """Edit plantation block attributes."""
    current_user = get_current_user()
    block = db.session.get(EstateBlock, block_id)
    if not block:
        flash("Block not found.", "danger")
        return redirect(url_for("farm.farm_list"))

    name = (request.form.get("name") or "").strip()
    area_str = request.form.get("area") or "0"
    unit = request.form.get("unit") or block.unit
    variety = (request.form.get("variety") or "").strip()
    location = (request.form.get("location") or "").strip()
    status = request.form.get("status") or block.status

    if not name or not variety:
        flash("Block name and variety cannot be empty.", "danger")
        return redirect(url_for("farm.farm_list"))

    try:
        area = Decimal(area_str)
        if area <= 0:
            flash("Area must be positive.", "danger")
            return redirect(url_for("farm.farm_list"))
    except Exception:
        flash("Invalid numerical area.", "danger")
        return redirect(url_for("farm.farm_list"))

    block.name = name
    block.area = area
    block.unit = unit
    block.variety = variety
    block.location = location
    block.status = status
    db.session.commit()

    log_audit(
        action="BLOCK_UPDATE",
        entity_type="EstateBlock",
        entity_id=str(block.id),
        outcome="SUCCESS",
        details=f"Updated block '{block.name}'",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Block '{block.name}' updated successfully.", "success")
    return redirect(url_for("farm.farm_list"))


@farm_bp.route("/farm/activity/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def log_activity():
    """Log agronomic or maintenance activity on a block."""
    current_user = get_current_user()
    block_id = request.form.get("block_id", type=int)
    activity_type = (request.form.get("activity_type") or "").strip()
    date_str = request.form.get("date") or str(date.today())
    input_quantity = (request.form.get("input_quantity") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    block = db.session.get(EstateBlock, block_id)
    if not block or not activity_type:
        flash("Please select a valid block and activity type.", "danger")
        return redirect(url_for("farm.farm_list"))

    try:
        act_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        act_date = date.today()

    activity = FarmActivity(
        block_id=block.id,
        activity_type=activity_type,
        date=act_date,
        input_quantity=input_quantity,
        notes=notes,
        responsible_user=current_user.username,
    )
    db.session.add(activity)
    db.session.commit()

    log_audit(
        action="FARM_ACTIVITY_LOGGED",
        entity_type="FarmActivity",
        entity_id=str(activity.id),
        outcome="SUCCESS",
        details=f"Logged {activity_type} on {block.name}",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Activity '{activity_type}' logged for {block.name}.", "success")
    return redirect(url_for("farm.farm_list"))
