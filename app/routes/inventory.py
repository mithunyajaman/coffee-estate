from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.database import db
from app.models.inventory import InventoryItem, StockTransaction
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

inventory_bp = Blueprint("inventory", __name__)

@inventory_bp.route("/inventory")
@login_required
def inventory_list():
    """Page 17: Inventory Management & Stock Ledger."""
    current_user = get_current_user()
    category_filter = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()
    low_stock_only = request.args.get("low_stock") == "1"
    page = request.args.get("page", 1, type=int)

    query = InventoryItem.query
    if search:
        query = query.filter(InventoryItem.name.ilike(f"%{search}%"))
    if category_filter:
        query = query.filter_by(category=category_filter)
    if low_stock_only:
        query = query.filter(InventoryItem.current_balance <= InventoryItem.reorder_level)

    pagination = query.order_by(InventoryItem.name.asc()).paginate(page=page, per_page=10, error_out=False)
    items = pagination.items

    # Recent transactions
    recent_txs = (
        StockTransaction.query.order_by(StockTransaction.date.desc(), StockTransaction.id.desc())
        .limit(10)
        .all()
    )

    # Categories
    categories = ["Fertilizers", "Crop Protection", "Tools & Equipment", "Processing Supplies", "Fuel & Oil"]

    # Low stock alert count
    all_items = InventoryItem.query.all()
    low_stock_count = sum(1 for it in all_items if it.is_low_stock)

    return render_template(
        "inventory.html",
        items=items,
        pagination=pagination,
        recent_txs=recent_txs,
        categories=categories,
        low_stock_count=low_stock_count,
        category_filter=category_filter,
        search=search,
        low_stock_only=low_stock_only,
        current_user=current_user,
    )


@inventory_bp.route("/inventory/item/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_item():
    """Add new inventory catalog item."""
    current_user = get_current_user()
    name = (request.form.get("name") or "").strip()
    category = (request.form.get("category") or "").strip()
    unit = (request.form.get("unit") or "").strip()
    init_qty_str = request.form.get("initial_quantity") or "0"
    reorder_str = request.form.get("reorder_level") or "10"
    location = (request.form.get("storage_location") or "").strip()

    if not name or not category or not unit:
        flash("Item name, category, and unit are required.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    existing = InventoryItem.query.filter_by(name=name).first()
    if existing:
        flash(f"An item named '{name}' already exists in inventory.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    try:
        init_qty = Decimal(init_qty_str)
        reorder_level = Decimal(reorder_str)
        if init_qty < 0 or reorder_level < 0:
            flash("Quantities and reorder levels cannot be negative.", "danger")
            return redirect(url_for("inventory.inventory_list"))
    except Exception:
        flash("Invalid numerical values.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    item = InventoryItem(
        name=name,
        category=category,
        unit=unit,
        current_balance=init_qty,
        reorder_level=reorder_level,
        storage_location=location,
    )
    db.session.add(item)
    db.session.flush()

    # If initial quantity > 0, log an initial stock IN transaction
    if init_qty > 0:
        tx = StockTransaction(
            item_id=item.id,
            type="IN",
            quantity=init_qty,
            date=date.today(),
            reference="Initial Stock Setup",
            authorized_by=current_user.username,
        )
        db.session.add(tx)

    db.session.commit()

    log_audit(
        action="INVENTORY_ITEM_CREATE",
        entity_type="InventoryItem",
        entity_id=str(item.id),
        outcome="SUCCESS",
        details=f"Created inventory item '{item.name}' (Category: {category}, Initial: {init_qty} {unit})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Item '{item.name}' added to inventory.", "success")
    return redirect(url_for("inventory.inventory_list"))


@inventory_bp.route("/inventory/transaction/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_transaction():
    """Record stock movements (IN / OUT / ADJUST) with strict negative balance prevention."""
    current_user = get_current_user()
    item_id = request.form.get("item_id", type=int)
    tx_type = request.form.get("type") # IN, OUT, ADJUST
    qty_str = request.form.get("quantity") or "0"
    ref = (request.form.get("reference") or "").strip()
    date_str = request.form.get("date") or str(date.today())

    item = db.session.get(InventoryItem, item_id)
    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    try:
        qty = Decimal(qty_str)
        if qty <= 0:
            flash("Transaction quantity must be greater than zero.", "danger")
            return redirect(url_for("inventory.inventory_list"))
    except Exception:
        flash("Invalid numerical quantity.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    try:
        tx_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        tx_date = date.today()

    # STRICT INVARIANT: NO NEGATIVE BALANCES
    if tx_type == "OUT":
        if qty > item.current_balance:
            flash(
                f"Transaction Rejected: Insufficient balance for '{item.name}'. "
                f"Requested OUT: {qty} {item.unit}, but current balance is only {item.current_balance} {item.unit}. "
                "Negative stock is not permitted.",
                "danger",
            )
            return redirect(url_for("inventory.inventory_list"))
        item.current_balance -= qty

    elif tx_type == "IN":
        item.current_balance += qty

    elif tx_type == "ADJUST":
        # Audit adjustment sets new balance directly; qty is target new balance
        item.current_balance = qty

    else:
        flash("Invalid transaction type specified.", "danger")
        return redirect(url_for("inventory.inventory_list"))

    # Record the immutable transaction record
    tx = StockTransaction(
        item_id=item.id,
        type=tx_type,
        quantity=qty,
        date=tx_date,
        reference=ref or "Manual Ledger Entry",
        authorized_by=current_user.username,
    )
    db.session.add(tx)
    db.session.commit()

    log_audit(
        action="STOCK_TRANSACTION",
        entity_type="StockTransaction",
        entity_id=str(tx.id),
        outcome="SUCCESS",
        details=f"Stock {tx_type}: {qty} {item.unit} for '{item.name}'. New Balance: {item.current_balance} {item.unit}",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(
        f"Stock {tx_type} of {qty} {item.unit} recorded for '{item.name}'. Current Balance: {item.current_balance} {item.unit}.",
        "success",
    )
    return redirect(url_for("inventory.inventory_list"))
