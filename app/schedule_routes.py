from flask import Blueprint, request, jsonify
from datetime import datetime
import pytz

from .deps import user_repo, task_repo, scheduler, calendar_client
from .models import Task
from .utils import parse_time
from .notifications_service import schedule_notification_reminders


schedule_bp = Blueprint("schedule", __name__)


@schedule_bp.post("/schedule_tasks")
def schedule_tasks_route():
    data = request.get_json()
    sub = data.get("sub")

    user = user_repo.find_by_sub(sub)
    if not user:
        return jsonify({"error": "User not found"}), 404

    tasks_data = task_repo.find_by_sub(sub)
    if not tasks_data or "tasks" not in tasks_data:
        return jsonify({"error": "No incomplete tasks found"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = calendar_client.get_primary_timezone(access_token)
    tz = pytz.timezone(user_timezone)

    incomplete_docs = [t for t in tasks_data["tasks"] if not t.get("isCompleted")]
    incomplete_tasks = [Task.from_mongo(t) for t in incomplete_docs]

    sorted_tasks = scheduler.sort_tasks(incomplete_tasks)
    top_tasks = sorted_tasks[:5]
    available_slots = scheduler.find_optimal_slots(access_token)
    scheduled_tasks = scheduler.schedule_tasks_in_slots(top_tasks, available_slots)

    calendar_id = "primary"
    event_responses = []

    for task in scheduled_tasks:
        start_date_str, start_time_str = task["start_time"].split(" ")
        end_date_str, end_time_str = task["end_time"].split(" ")

        start_time = parse_time(
            start_time_str,
            datetime.strptime(start_date_str, "%Y-%m-%d"),
            tz,
        )
        end_time = parse_time(
            end_time_str,
            datetime.strptime(end_date_str, "%Y-%m-%d"),
            tz,
        )

        event_details = {
            "summary": f"{task['task']} 💙 TimeFinder",
            "start": {"dateTime": start_time.isoformat(), "timeZone": user_timezone},
            "end": {"dateTime": end_time.isoformat(), "timeZone": user_timezone},
            "colorId": "5",
        }

        response = calendar_client.create_event(access_token, calendar_id, event_details)
        event_responses.append(response)

        task_repo.mark_task_scheduled(sub, task["id"], start_time, end_time)

    return jsonify(
        {
            "scheduled_tasks": [t["task"] for t in scheduled_tasks],
            "calendar_responses": event_responses,
        }
    )


@schedule_bp.post("/schedule_notifications")
def handle_schedule_notifications():
    data = request.get_json()
    sub = data.get("sub")

    user = user_repo.find_by_sub(sub)
    if not user:
        return jsonify({"error": "User not found"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = calendar_client.get_primary_timezone(access_token)
    responses = schedule_notification_reminders(access_token, user_timezone)

    return jsonify({"scheduled_notifications": responses})



@schedule_bp.post("/user_calendar_events")
def get_user_calendar_events():
    data = request.get_json()
    sub = data.get("sub")
    if not sub:
        return jsonify({"error": "Missing 'sub' in request"}), 400

    user = user_repo.find_by_sub(sub)
    if not user:
        return jsonify({"error": "User not found"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = calendar_client.get_primary_timezone(access_token)
    tz = pytz.timezone(user_timezone)

    today = datetime.now(tz)
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    params = {
        "timeMin": start_of_day,
        "timeMax": end_of_day,
        "singleEvents": True,
        "orderBy": "startTime",
    }

    try:
        events = calendar_client.list_events(access_token, "primary", params)
    except Exception as e:
        return jsonify({"error": "Failed to fetch events", "details": str(e)}), 500

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})

        start_time = start.get("dateTime", start.get("date"))
        end_time = end.get("dateTime", end.get("date"))

        if not start_time or not end_time or "T" not in start_time:
            continue

        date_part, time_part = start_time.split("T")
        end_date_part, end_time_part = end_time.split("T")

        start_dt = parse_time(time_part[:5], datetime.fromisoformat(date_part), tz)
        end_dt = parse_time(end_time_part[:5], datetime.fromisoformat(end_date_part), tz)

        event["start"]["dateTime"] = start_dt.isoformat()
        event["end"]["dateTime"] = end_dt.isoformat()

    return jsonify(events), 200

def parse_time(time_str, date, tz):
    
    try:
        time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        time = datetime.strptime(time_str, "%H:%M:%S").time()
    return tz.localize(datetime.combine(date, time))


