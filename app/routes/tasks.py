from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.database import db
from app.models.task import Task
from app.models.farm import EstateBlock
from app.models.employee import Employee
from app.services.auth_service import login_required, roles_required, get_current_user
from app.services.audit_service import log_audit

tasks_bp = Blueprint("tasks", __name__)

@tasks_bp.route("/tasks")
@login_required
def task_list():
    """Page 14: Task Management."""
    current_user = get_current_user()
    status_filter = request.args.get("status", "").strip()
    priority_filter = request.args.get("priority", "").strip()
    block_filter = request.args.get("block_id", type=int)
    page = request.args.get("page", 1, type=int)

    query = Task.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if block_filter:
        query = query.filter_by(block_id=block_filter)

    # If regular employee, filter to their assigned tasks if linked
    if current_user.is_employee and current_user.employee_code:
        emp = Employee.query.filter_by(employee_code=current_user.employee_code).first()
        if emp:
            query = query.filter_by(assigned_to_id=emp.id)

    pagination = query.order_by(Task.due_date.asc(), Task.id.desc()).paginate(page=page, per_page=10, error_out=False)
    tasks = pagination.items

    blocks = EstateBlock.query.order_by(EstateBlock.name.asc()).all()
    employees = Employee.query.filter_by(status="Active").order_by(Employee.name.asc()).all()

    # Counts
    pending_count = Task.query.filter_by(status="Pending").count()
    in_progress_count = Task.query.filter_by(status="In Progress").count()
    completed_count = Task.query.filter_by(status="Completed").count()

    return render_template(
        "tasks.html",
        tasks=tasks,
        pagination=pagination,
        blocks=blocks,
        employees=employees,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
        status_filter=status_filter,
        priority_filter=priority_filter,
        block_filter=block_filter,
        current_user=current_user,
    )


@tasks_bp.route("/tasks/add", methods=["POST"])
@roles_required("Admin", "Estate Manager")
def add_task():
    """Create and assign field or processing task."""
    current_user = get_current_user()
    title = (request.form.get("title") or "").strip()
    instructions = (request.form.get("instructions") or "").strip()
    block_id = request.form.get("block_id", type=int) or None
    assigned_to_id = request.form.get("assigned_to_id", type=int) or None
    due_date_str = request.form.get("due_date") or None
    priority = request.form.get("priority") or "Medium"

    if not title:
        flash("Task title is required.", "danger")
        return redirect(url_for("tasks.task_list"))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    task = Task(
        title=title,
        instructions=instructions,
        block_id=block_id,
        assigned_to_id=assigned_to_id,
        due_date=due_date,
        priority=priority,
        status="Pending",
    )
    db.session.add(task)
    db.session.commit()

    log_audit(
        action="TASK_CREATE",
        entity_type="Task",
        entity_id=str(task.id),
        outcome="SUCCESS",
        details=f"Created task '{task.title}' (Priority: {priority}, Assigned to ID: {assigned_to_id})",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Task '{task.title}' assigned successfully.", "success")
    return redirect(url_for("tasks.task_list"))


@tasks_bp.route("/tasks/<int:task_id>/update-status", methods=["POST"])
@login_required
def update_task_status(task_id):
    """Update task status (allowed by assignee or management)."""
    current_user = get_current_user()
    task = db.session.get(Task, task_id)
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for("tasks.task_list"))

    # If employee, verify they are the assigned worker
    if current_user.is_employee:
        emp = Employee.query.filter_by(employee_code=current_user.employee_code).first()
        if not emp or task.assigned_to_id != emp.id:
            flash("You can only update tasks assigned to your employee ID.", "danger")
            return redirect(url_for("tasks.task_list"))

    new_status = request.form.get("status") or task.status
    notes = (request.form.get("completion_notes") or "").strip()

    old_status = task.status
    task.status = new_status
    if notes:
        task.completion_notes = notes
    db.session.commit()

    log_audit(
        action="TASK_STATUS_UPDATE",
        entity_type="Task",
        entity_id=str(task.id),
        outcome="SUCCESS",
        details=f"Task #{task.id} '{task.title}' status changed from '{old_status}' to '{new_status}'",
        actor_id=current_user.id,
        actor_username=current_user.username,
    )

    flash(f"Task #{task.id} updated to '{new_status}'.", "success")
    return redirect(url_for("tasks.task_list"))
