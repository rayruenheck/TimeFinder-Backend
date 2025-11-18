from flask import Blueprint, request, jsonify
from datetime import datetime

from .deps import task_repo

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.post("/tasks")
def create_or_update_tasks():
    data = request.get_json()

    if not data or "tasks" not in data or "sub" not in data:
        return jsonify(message="Missing required data"), 400

    tasks = data["tasks"]
    sub = data["sub"]
    today_date = datetime.now().strftime("%Y-%m-%d")

    result = task_repo.upsert_task_cluster(sub, tasks)

    if result.matched_count > 0 or result.upserted_id is not None:
        action = "updated" if result.matched_count > 0 else "created"
        return (
            jsonify(message=f"Task cluster {action} successfully on {today_date}"),
            200 if action == "updated" else 201,
        )
    else:
        return jsonify(message="No changes made to task cluster"), 200


@tasks_bp.post("/add-task")
def add_task():
    data = request.get_json()

    if not data or "task" not in data or "sub" not in data:
        return jsonify(message="Missing required data"), 400

    task = data["task"]
    sub = data["sub"]

    result = task_repo.add_single_task(sub, task)

    if result.matched_count > 0 or result.upserted_id is not None:
        return jsonify(message="Task added successfully"), 201
    else:
        return jsonify(message="Task not added"), 500


@tasks_bp.get("/get-tasks")
def get_tasks():
    sub = request.args.get("sub")
    if not sub:
        return jsonify({"message": "Missing 'sub' in request"}), 400

    tasks_data = task_repo.find_by_sub(sub)
    if not tasks_data:
        return jsonify({"message": "No tasks found for the user"}), 404

    return jsonify({"tasks": tasks_data.get("tasks", [])}), 200


@tasks_bp.post("/update-completion")
def update_task_completion():
    data = request.get_json()
    if not data or "id" not in data or "isCompleted" not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400

    task_id = data["id"]
    is_completed = data["isCompleted"]

    result = task_repo.update_task_completion(task_id, is_completed)

    if result.modified_count > 0:
        return jsonify({"status": "success", "message": "Task updated successfully."}), 200
    else:
        return jsonify({"status": "error", "message": "Task not found or no changes made."}), 404