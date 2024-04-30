from flask import request, jsonify, session
import pytz
import requests
from datetime import datetime, timedelta
from . import users_bp
from bson.json_util import dumps
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv
load_dotenv()

uri = os.getenv("MONGODB_URI")

client = MongoClient(uri, server_api=ServerApi('1'))
db = client["timefinder"] 

GOOGLE_CALENDAR_API_BASE_URL = os.getenv("GOOGLE_CALENDAR_API_BASE_URL")


users_collection = db.users
tasks_collection = db.tasks


@users_bp.post('/users')
def create_or_update_user():
    user_data = request.get_json()
    
    if not user_data or 'email' not in user_data:
        return jsonify(message="Missing required user data"), 400

    email = user_data['email']
    
    result = users_collection.update_one(
        {"email": email},  
        {"$set": user_data},  
        upsert=True  
    )
    
    
    if result.matched_count > 0:
        return jsonify(message="User updated successfully"), 200
    elif result.upserted_id is not None:
        return jsonify(message="User created successfully"), 201
    else:
        return jsonify(message="User not created or updated"), 500
    

@users_bp.post('/tasks')
def create_or_update_tasks():
    data = request.get_json()

    if not data or 'tasks' not in data or 'userId' not in data:
        return jsonify(message="Missing required data"), 400

    tasks = data['tasks']
    userId = data['userId']
    today_date = datetime.now().strftime("%Y-%m-%d")
    session['userId'] = userId   

    
    result = tasks_collection.update_one(
        {"userId": userId,},
        {"$set": {"tasks": tasks, "date": today_date}},
        upsert=True
    )

    
    if result.matched_count > 0 or result.upserted_id is not None:
        action = "updated" if result.matched_count > 0 else "created"
        return jsonify(message=f"Task cluster {action} successfully on {today_date}"), 200 if action == "updated" else 201
    else:
        return jsonify(message="No changes made to task cluster"), 200


def parse_time(time_str, date, tz):
    """Converts a time string to a timezone-aware datetime object."""
    return tz.localize(datetime.combine(date, datetime.strptime(time_str, "%H:%M").time()))

def get_user_timezone(access_token):
    """Fetches the user's timezone from their Google Calendar settings."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/users/me/calendarList/primary", headers=headers)
    return response.json().get('timeZone', 'UTC') if response.status_code == 200 else 'UTC'

def get_concentration_time(access_token):
    """Retrieves user-specific concentration times from the database."""
    user_data = users_collection.find_one({"accessToken": access_token})
    if user_data and "concentration_time" in user_data:
        times = user_data["concentration_time"]
        return (times["start"], times["end"])
    return None

@users_bp.post('/concentration_time')
def update_concentration_time():
    data = request.get_json()
    if not data or 'user_id' not in data or 'start' not in data or 'end' not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400

    user_id = data['user_id']
    start = data['start']
    end = data['end']

    
    users_collection.update_one(
        {"idToken": user_id},
        {"$set": {"concentration_time": {"start": start, "end": end}}},
        upsert=True
    )
    return jsonify({"status": "success", "message": "Concentration times updated.", "concentration_time": {"start": start, "end": end}})

@users_bp.post('/schedule_tasks')
def schedule_tasks():
    """Endpoint to schedule tasks based on user availability and concentration times."""
    data = request.get_json()
    user = users_collection.find_one({"idToken": data.get("userId")})
    if not user:
        return jsonify({"error": "User not found"}), 404

    tasks = tasks_collection.find_one({"userId": data.get("userId"), "date": datetime.now().strftime("%Y-%m-%d")})
    if not tasks or 'tasks' not in tasks:
        return jsonify({"error": "No tasks found for today"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    sorted_tasks = sort_tasks(tasks['tasks'])
    
    events = find_optimal_slots(access_token)
    
    scheduled_tasks = schedule_tasks_in_slots(sorted_tasks, events)
    
    

    return jsonify({"scheduled_tasks": scheduled_tasks})

def find_optimal_slots(access_token):
    """Identifies open time slots by checking Google Calendar events against user concentration times."""
    """Identifies open time slots by checking Google Calendar events against user concentration times."""
    user_timezone = get_user_timezone(access_token)
    local_timezone = pytz.timezone(user_timezone)
    today = datetime.now(tz=local_timezone).strftime('%Y-%m-%d')
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers={
        "Authorization": f"Bearer {access_token}"
    }, params={"timeMin": f"{today}T00:00:00Z", "timeMax": f"{today}T23:59:59Z", "singleEvents": True, "orderBy": "startTime"})

    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers={
        "Authorization": f"Bearer {access_token}"
    }, params={"timeMin": f"{today}T00:00:00Z", "timeMax": f"{today}T23:59:59Z", "singleEvents": True, "orderBy": "startTime"})

    if response.status_code != 200:
        return {"error": "Failed to fetch calendar events", "details": response.text}

    events = response.json().get('items', [])
    slots = [(local_timezone.localize(datetime.strptime(f"{today} 08:00", '%Y-%m-%d %H:%M')),
              local_timezone.localize(datetime.strptime(f"{today} 20:00", '%Y-%m-%d %H:%M')))]

    for event in events:
        event_start = datetime.fromisoformat(event['start']['dateTime']).astimezone(local_timezone)
        event_end = datetime.fromisoformat(event['end']['dateTime']).astimezone(local_timezone)
        event_start = datetime.fromisoformat(event['start']['dateTime']).astimezone(local_timezone)
        event_end = datetime.fromisoformat(event['end']['dateTime']).astimezone(local_timezone)
        new_slots = []
        for slot in slots:
            new_slots.extend(adjust_slot_for_event(slot, event_start, event_end))
            new_slots.extend(adjust_slot_for_event(slot, event_start, event_end))
        slots = new_slots

    return calculate_slot_status(slots, access_token, user_timezone)

def calculate_slot_status(slots, access_token, timezone):
    """Determines the status of each slot regarding availability and concentration alignment, breaking down into 30-minute intervals."""
    all_slots = []
    user_concentration_times = get_concentration_time(access_token)
    tz = pytz.timezone(timezone)
    today_date = datetime.now(tz).date()

    for slot_start, slot_end in slots:
        current_time = slot_start
        while current_time < slot_end:
            slot_end_interval = min(current_time + timedelta(minutes=30), slot_end)
            is_concentration_time = False
            if user_concentration_times:
                user_start_datetime = parse_time(user_concentration_times[0], today_date, tz)
                user_end_datetime = parse_time(user_concentration_times[1], today_date, tz)
                is_concentration_time = user_start_datetime <= current_time and slot_end_interval <= user_end_datetime

            all_slots.append({
                'start': current_time,
                'end': slot_end_interval,
                'available': True,
                'concentration_time': is_concentration_time
            })
            current_time += timedelta(minutes=30)
    

    return all_slots

def adjust_slot_for_event(slot, event_start, event_end):
    """Adjusts slots based on overlapping with an event."""
    slot_start, slot_end = slot
    new_slots = []
    if slot_start < event_start:
        new_slots.append((slot_start, min(slot_end, event_start)))
    if slot_end > event_end:
        new_slots.append((max(slot_start, event_end), slot_end))
    return new_slots if new_slots else [slot]

def sort_tasks(tasks):
    """Sort tasks by priority and concentration."""
    # High priority and high concentration tasks first
    return sorted(tasks, key=lambda x: (x['priority'], x['concentration']), reverse=True)

def schedule_tasks_in_slots(sorted_tasks, available_slots):
    scheduled_tasks = []
    for task in sorted_tasks:
        for slot in available_slots:
            if slot['available'] and fits_time_slot(task, slot, available_slots):
                start_time = slot['start'].strftime('%Y-%m-%d %H:%M:%S')
                end_time = (slot['start'] + timedelta(minutes=int(task['time']))).strftime('%Y-%m-%d %H:%M:%S')
                scheduled_tasks.append({
                    'task': task['name'],
                    'start_time': start_time,
                    'end_time': end_time
                })
                # Mark slots as used
                task_duration = timedelta(minutes=int(task['time']))
                accumulated_time = timedelta()
                for i in range(available_slots.index(slot), len(available_slots)):
                    if accumulated_time >= task_duration:
                        break
                    available_slots[i]['available'] = False
                    accumulated_time += available_slots[i]['end'] - available_slots[i]['start']
                break
    return scheduled_tasks

def fits_time_slot(task, slot, available_slots):
    """Check if the task can be scheduled starting from this slot, potentially using multiple slots."""
    task_duration = timedelta(minutes=int(task['time']))
    start_index = available_slots.index(slot)
    accumulated_time = timedelta()

    # Attempt to accumulate enough time across consecutive slots
    for i in range(start_index, len(available_slots)):
        if not available_slots[i]['available']:
            break
        current_slot_duration = available_slots[i]['end'] - available_slots[i]['start']
        accumulated_time += current_slot_duration
        if accumulated_time >= task_duration:
            return True
    return False

def calculate_end_time(start_time_str, task_duration_minutes):
    """Calculate the end time of a task given its start time and duration in minutes."""
    start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    task_duration = timedelta(minutes=int(task_duration_minutes))
    end_time = start_time + task_duration
    return end_time.strftime('%Y-%m-%d %H:%M:%S')



def update_slot_availability(slots, chosen_slot, task_time):
    """Update slot availability after scheduling a task."""
    # Reduce the duration of the chosen slot
    start_time = chosen_slot['start']
    end_time = start_time + timedelta(minutes=int(task_time))
    chosen_slot['start'] = end_time
    if chosen_slot['start'] >= chosen_slot['end']:
        slots.remove(chosen_slot)

# @users_bp.route('/get_primary_calendar_id', methods=['POST'])
# def get_primary_calendar_id():
#     """
#     API endpoint that fetches the primary calendar ID for the user.
#     Expects a JSON payload with an 'access_token'.
#     """
#     data = request.get_json()
#     access_token = data.get('access_token')
#     if not access_token:
#         return jsonify({"error": "Access token is required"}), 400
    
#     headers = {"Authorization": f"Bearer {access_token}"}
#     response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/users/me/calendarList", headers=headers)
#     if response.status_code == 200:
#         calendars = response.json().get('items', [])
#         for calendar in calendars:
#             if calendar.get('primary', False):  
#                 return jsonify({"calendar_id": calendar.get('id', 'primary')})  
#         return jsonify({"calendar_id": "primary"}), 200  
#     else:
#         return jsonify({"error": "Failed to retrieve calendar information", "status_code": response.status_code}), 500
