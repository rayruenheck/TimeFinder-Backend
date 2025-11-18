from flask import Blueprint, request, jsonify
from .deps import user_repo

users_bp = Blueprint("users", __name__)


@users_bp.post("/users")
def create_or_update_user():
    user_data = request.get_json()
    
    if not user_data or "email" not in user_data:
        return jsonify(message="Missing required user data"), 400

    try:
        result = user_repo.upsert_user(user_data)
    except ValueError as e:
        return jsonify(message=str(e)), 400

    if result.matched_count > 0:
        return jsonify(message="User updated successfully"), 200
    elif result.upserted_id is not None:
        return jsonify(message="User created successfully"), 201
    else:
        return jsonify(message="User not created or updated"), 500


@users_bp.post("/concentration_time")
def update_concentration_time():
    data = request.get_json()
    if not data or "sub" not in data or "start" not in data or "end" not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400

    sub = data["sub"]
    start = data["start"]
    end = data["end"]

    user_repo.upsert_concentration_time(sub, start, end)

    return jsonify({
        "status": "success",
        "message": "Concentration times updated.",
        "concentration_time": {"start": start, "end": end},
    })