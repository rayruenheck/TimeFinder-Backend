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
    




@users_bp.route('/schedule_tasks', methods=['POST'])
def schedule_tasks():
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

    events = find_optimal_slots(access_token)
    return jsonify({"events": events})


def get_concentration_time(access_token):
    user_data = users_collection.find_one({"idToken": access_token})
    if user_data and "concentration_time" in user_data:
        concentration_time = user_data["concentration_time"]
        start_time = datetime.strptime(concentration_time["start"], "%H:%M").time()
        end_time = datetime.strptime(concentration_time["end"], "%H:%M").time()
        return (start_time, end_time)
    else:
        return None
    

@users_bp.post('/concentration_time')
def update_concentration_time():
    data = request.get_json()
    if not data or 'user_id' not in data or 'start' not in data or 'end' not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400
    
    user_id = data['user_id']
    start = data['start']
    end = data['end']
    
    if not get_concentration_time(user_id):
        users_collection.update_one(
            {"idToken": user_id},
            {"$set": {"concentration_time": {"start": start, "end": end}}},
            upsert=True  # Create the document if it does not exist
        )
    
    return jsonify({
        "status": "success",
        "message": "Concentration times updated.",
        "concentration_time": {"start": start, "end": end}
    })



def adjust_timezone(date_string):
    parts = date_string.rsplit(':', 1)
    if len(parts[1]) == 1:  
        return f"{parts[0]}:0{parts[1]}"  
    return date_string


def get_user_timezone(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/users/me/calendarList/primary", headers=headers)
    if response.status_code == 200:
        return response.json().get('timeZone', 'UTC')  # Default to UTC if not found
    return 'UTC'  # Default timezone if API call fails


def adjust_slot_for_event(slot, event_start, event_end):
    """Adjust slots based on overlapping with an event."""
    slot_start, slot_end = slot
    new_slots = []
    if slot_start < event_start:
        new_slots.append((slot_start, min(event_start, slot_end)))
    if slot_end > event_end:
        new_slots.append((max(event_end, slot_start), slot_end))
    return new_slots if new_slots else [slot]

def calculate_slot_status(slots, access_token, timezone):
    all_slots = {}
    user_concentration_times = get_concentration_time(access_token)
    user_start_time, user_end_time = (None, None) if not user_concentration_times else user_concentration_times
    user_start_datetime = ''
    user_end_datetime = ''

    # Ensure user times are localized to the specified timezone if needed
    if user_start_time and user_end_time:
        # Parse times to full datetime objects with today's date for accurate comparison
        today_date = datetime.now(timezone).date()
        user_start_datetime = timezone.localize(datetime.combine(today_date, user_start_time))
        user_end_datetime = timezone.localize(datetime.combine(today_date, user_end_time))

    for slot_start, slot_end in slots:
        # Ensure slots are in the correct timezone
        slot_start_local = slot_start.astimezone(timezone)
        slot_end_local = slot_end.astimezone(timezone)

        time_range = f"{slot_start_local.strftime('%H:%M')} - {slot_end_local.strftime('%H:%M')}"

        is_concentration_time = False
        if user_start_datetime and user_end_datetime:
            # Check if the slot is entirely within the user's concentration time
            is_concentration_time = user_start_datetime <= slot_start_local <= user_end_datetime and user_end_datetime >= slot_end_local

        all_slots[time_range] = {
            'available': True,  
            'concentration_time': is_concentration_time
        }

    return all_slots

def find_optimal_slots(access_token):
    """Find optimal slots free from events and check against user concentration times."""
    user_timezone = get_user_timezone(access_token)
    local_timezone = pytz.timezone(user_timezone)
    headers = {"Authorization": f"Bearer {access_token}"}
    today = datetime.now(tz=local_timezone).strftime('%Y-%m-%d')
    params = {
        "timeMin": f"{today}T00:00:00Z",
        "timeMax": f"{today}T23:59:59Z",
        "singleEvents": True,
        "orderBy": "startTime"
    }
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers=headers, params=params)
    if response.status_code != 200:
        return {"error": "Failed to fetch calendar events", "details": response.text}

    events = response.json().get('items', [])
    slots = [(local_timezone.localize(datetime.strptime(f"{today} 00:00", '%Y-%m-%d %H:%M')),
              local_timezone.localize(datetime.strptime(f"{today} 23:59", '%Y-%m-%d %H:%M')))]

    for event in events:
        start = datetime.fromisoformat(adjust_timezone(event['start']['dateTime'])).astimezone(local_timezone)
        end = datetime.fromisoformat(adjust_timezone(event['end']['dateTime'])).astimezone(local_timezone)
        new_slots = []
        for slot in slots:
            new_slots.extend(adjust_slot_for_event(slot, start, end))
        slots = new_slots

    return calculate_slot_status(slots, access_token, local_timezone)