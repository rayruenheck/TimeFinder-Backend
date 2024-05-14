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



# CREATING AND UPDATING TASK AND USER INFO


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

    if not data or 'tasks' not in data or 'sub' not in data:
        return jsonify(message="Missing required data"), 400

    tasks = data['tasks']
    sub = data['sub']
    today_date = datetime.now().strftime("%Y-%m-%d")
   

    # Append new tasks to the existing tasks array for the same day and user
    result = tasks_collection.update_one(
        {"sub": sub, "date": today_date},  # Ensure the update is for the same day and user
        {"$addToSet": {"tasks": {"$each": tasks}}},  # Append all new tasks
        upsert=True
    )

    if result.matched_count > 0 or result.upserted_id is not None:
        action = "updated" if result.matched_count > 0 else "created"
        return jsonify(message=f"Task cluster {action} successfully on {today_date}"), 200 if action == "updated" else 201
    else:
        return jsonify(message="No changes made to task cluster"), 200


@users_bp.get('/get-tasks')
def get_tasks():
    sub = request.args.get('sub')
    if not sub:
        return jsonify({"message": "Missing 'sub' in request"}), 400

    # Retrieve tasks for the given 'sub'
    tasks_data = tasks_collection.find_one({"sub": sub})
    if not tasks_data:
        return jsonify({"message": "No tasks found for the user"}), 404

    return jsonify({"tasks": tasks_data.get('tasks', [])}), 200



@users_bp.post('/concentration_time')
def update_concentration_time():
    data = request.get_json()
    if not data or 'sub' not in data or 'start' not in data or 'end' not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400

    sub = data['sub']
    start = data['start']
    end = data['end']

    
    users_collection.update_one(
        {"sub": sub},
        {"$set": {"concentration_time": {"start": start, "end": end}}},
        upsert=True
    )
    return jsonify({"status": "success", "message": "Concentration times updated.", "concentration_time": {"start": start, "end": end}})

@users_bp.route('/update-completion', methods=['POST'])
def update_task_completion():
    data = request.get_json()
    if not data or 'id' not in data or 'isCompleted' not in data:
        return jsonify({"status": "error", "message": "Invalid data provided."}), 400

    task_id = data['id']
    is_completed = data['isCompleted']

    # Update the task's 'isCompleted' status in the database
    result = tasks_collection.update_one(
        {"tasks.id": task_id},  # Assuming tasks are stored with an 'id' field in an array under a document
        {"$set": {"tasks.$.isCompleted": is_completed}}
    )

    if result.modified_count > 0:
        return jsonify({"status": "success", "message": "Task updated successfully."}), 200
    else:
        return jsonify({"status": "error", "message": "Task not found or no changes made."}), 404

# SCHEDULING AND SCHEDULING LOGIC

def parse_time(time_str, date, tz):
    
    try:
        time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        time = datetime.strptime(time_str, "%H:%M:%S").time()
    return tz.localize(datetime.combine(date, time))



def get_concentration_time(access_token):
    user_data = users_collection.find_one({"accessToken": access_token})
    if user_data and "concentration_time" in user_data:
        times = user_data["concentration_time"]
        return (times["start"], times["end"])
    return None


def get_user_timezone(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/users/me/calendarList/primary", headers=headers)
    return response.json().get('timeZone', 'UTC') if response.status_code == 200 else 'UTC'


def create_calendar_event(access_token, calendar_id, event_details):
    url = f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/{calendar_id}/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=event_details)
    return response.json()


@users_bp.route('/schedule_notifications', methods=['POST'])
def handle_schedule_notifications():
    data = request.get_json()
    user = users_collection.find_one({"sub": data.get("sub")})
    if not user:
        return jsonify({"error": "User not found"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = get_user_timezone(access_token)
    responses = schedule_notification_reminders(access_token, user_timezone)
    return jsonify({"scheduled_notifications": responses})


@users_bp.post('/schedule_tasks')
def schedule_tasks():
    data = request.get_json()
    user = users_collection.find_one({"sub": data.get("sub")})
    if not user:
        return jsonify({"error": "User not found"}), 404

    tasks_data = tasks_collection.find_one({"sub": data.get("sub"), "tasks.isCompleted": False})
    if not tasks_data or 'tasks' not in tasks_data:
        return jsonify({"error": "No tasks found for today"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = get_user_timezone(access_token)
    tz = pytz.timezone(user_timezone)

    sorted_tasks = sort_tasks(tasks_data['tasks'])
    top_tasks = sorted_tasks[:5]
    events = find_optimal_slots(access_token)
    scheduled_tasks = schedule_tasks_in_slots(top_tasks, events)

    calendar_id = 'primary'
    event_responses = []
    for task in scheduled_tasks:
        start_time = parse_time(task['start_time'].split(' ')[1], datetime.strptime(task['start_time'].split(' ')[0], '%Y-%m-%d'), tz)
        end_time = parse_time(task['end_time'].split(' ')[1], datetime.strptime(task['end_time'].split(' ')[0], '%Y-%m-%d'), tz)
        event_details = {
            'summary': f"{task['task']} 💙 TimeFinder",
            'start': {'dateTime': start_time.isoformat(), 'timeZone': user_timezone},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': user_timezone},
            'colorId': '5'
        }
        response = create_calendar_event(access_token, calendar_id, event_details)
        event_responses.append(response)

        tasks_collection.update_one(
            {"sub": data.get("sub"), 'tasks.id': task['id']},
            {"$set": {"tasks.$.isScheduled": True}}
        )

    return jsonify({"scheduled_tasks": [task['task'] for task in scheduled_tasks], "calendar_responses": event_responses})


def find_optimal_slots(access_token):
    """Identifies open time slots by checking Google Calendar events against user concentration times."""
    user_timezone = get_user_timezone(access_token)
    local_timezone = pytz.timezone(user_timezone)
    today = datetime.now(tz=local_timezone).strftime('%Y-%m-%d')
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers={
        "Authorization": f"Bearer {access_token}"
    }, params={"timeMin": f"{today}T00:00:00Z", "timeMax": f"{today}T23:59:59Z", "singleEvents": True, "orderBy": "startTime"})

    if response.status_code != 200:
        return {"error": "Failed to fetch calendar events", "details": response.text}

    events = response.json().get('items', [])
    slots = [(local_timezone.localize(datetime.strptime(f"{today} 08:00", '%Y-%m-%d %H:%M')),
              local_timezone.localize(datetime.strptime(f"{today} 20:00", '%Y-%m-%d %H:%M')))]

    buffer_minutes = 10
    buffer_duration = timedelta(minutes=buffer_minutes)

    for event in events:
        event_start = datetime.fromisoformat(event['start']['dateTime']).astimezone(local_timezone) 
        event_end = datetime.fromisoformat(event['end']['dateTime']).astimezone(local_timezone) + buffer_duration

        new_slots = []
        for slot in slots:
            new_slots.extend(adjust_slot_for_event(slot, event_start, event_end))
        slots = new_slots

    return calculate_slot_status(slots, access_token, user_timezone)


def calculate_slot_status(slots, access_token, timezone):
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
    """Adjust slots based on event times with a buffer period."""
    slot_start, slot_end = slot
    new_slots = []
    if slot_start < event_start:
        new_slots.append((slot_start, min(slot_end, event_start)))
    if slot_end > event_end:
        new_slots.append((max(slot_start, event_end), slot_end))
    return new_slots if new_slots else [slot]


def sort_tasks(tasks):
    priority_map = {'high': 3, 'medium': 2, 'low': 1}
    return sorted(tasks, key=lambda task: priority_map[task['priority']], reverse=True)


def schedule_tasks_in_slots(sorted_tasks, available_slots):
    scheduled_tasks = []
    medium_concentration_tasks = []

    for task in sorted_tasks:
        if task['concentration'] == 'high':
            target_slots = [slot for slot in available_slots if slot['concentration_time'] and slot['available']]
        elif task['concentration'] == 'low':
            target_slots = [slot for slot in available_slots if not slot['concentration_time'] and slot['available']]
        else:
            medium_concentration_tasks.append(task)
            continue

        for slot in target_slots:
            if fits_time_slot(task, slot, available_slots):
                schedule_task(task, slot, scheduled_tasks, available_slots)
                break

    for task in medium_concentration_tasks:
        target_slots = [slot for slot in available_slots if slot['concentration_time'] and slot['available']]
        scheduled = False
        for slot in target_slots:
            if fits_time_slot(task, slot, available_slots):
                schedule_task(task, slot, scheduled_tasks, available_slots)
                scheduled = True
                break

        if not scheduled:
            for slot in [slot for slot in available_slots if slot['available']]:
                if fits_time_slot(task, slot, available_slots):
                    schedule_task(task, slot, scheduled_tasks, available_slots)
                    break

    return scheduled_tasks


def fits_time_slot(task, slot, available_slots):
    """Check if the task can be scheduled starting from this slot, potentially using multiple slots."""
    buffer_minutes = 10
    buffer_duration = timedelta(minutes=buffer_minutes)
    task_duration = timedelta(minutes=int(task['time']))
    required_duration = task_duration + buffer_duration  

    start_index = available_slots.index(slot)
    accumulated_time = timedelta()

    for i in range(start_index, len(available_slots)):
        if not available_slots[i]['available']:
            break
        current_slot_duration = available_slots[i]['end'] - available_slots[i]['start']
        accumulated_time += current_slot_duration
        if accumulated_time >= required_duration:
            return True
    return False

def mark_slots_as_used(start_time, end_time, slots):
    """Mark slots as used, including a 10-minute buffer."""
    buffer_minutes = 10
    buffer_duration = timedelta(minutes=buffer_minutes)

    adjusted_start = start_time 
    adjusted_end = end_time + buffer_duration

    for slot in slots:
        slot_start = slot['start']
        slot_end = slot['end']
        if slot_start < adjusted_end and slot_end > adjusted_start:
            slot['available'] = False

def schedule_task(task, slot, scheduled_tasks, available_slots):
   

    start_time = slot['start']   
    end_time = start_time + timedelta(minutes=int(task['time']))

    scheduled_tasks.append({
        'task': task['name'],
        'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'id': task['id'],
        'isCompleted': task['isCompleted'],
        'isScheduled': task['isScheduled']
    })

    # Update slots as used including buffer time
    mark_slots_as_used(start_time, end_time, available_slots)
    
def calculate_end_time(start_time_str, task_duration_minutes):
    """Calculate the end time of a task given its start time and duration in minutes."""
    start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    task_duration = timedelta(minutes=int(task_duration_minutes))
    end_time = start_time + task_duration
    return end_time.strftime('%Y-%m-%d %H:%M:%S')


@users_bp.post('/user_calendar_events')
def get_user_calendar_events():
    data = request.get_json()
    if 'sub' not in data:
        return jsonify({"error": "Missing 'sub' in request"}), 400

    user = users_collection.find_one({"sub": data.get("sub")})
    if not user:
        return jsonify({"error": "User not found"}), 404

    access_token = user.get("accessToken")
    if not access_token:
        return jsonify({"error": "Missing access token"}), 400

    user_timezone = get_user_timezone(access_token)
    tz = pytz.timezone(user_timezone)

    headers = {"Authorization": f"Bearer {access_token}"}
    today = datetime.now(tz)
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    params = {
        "timeMin": start_of_day,
        "timeMax": end_of_day,
        "singleEvents": True,
        "orderBy": "startTime"
    }

    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers=headers, params=params)

    if response.status_code == 200:
        events = response.json().get('items', [])
        for event in events:
            start_time = event.get('start').get('dateTime', event.get('start').get('date'))
            end_time = event.get('end').get('dateTime', event.get('end').get('date'))
            event['start']['dateTime'] = parse_time(start_time.split('T')[1][:5], datetime.fromisoformat(start_time.split('T')[0]), tz).isoformat()
            event['end']['dateTime'] = parse_time(end_time.split('T')[1][:5], datetime.fromisoformat(end_time.split('T')[0]), tz).isoformat()
        return jsonify(events), 200
    else:
        return jsonify({"error": "Failed to fetch events", "details": response.text}), response.status_code


def schedule_notification_reminders(access_token, user_timezone):
    tz = pytz.timezone(user_timezone)
    calendar_id = 'primary'
    responses = []

    start_date = datetime.now(tz)
    end_date = start_date + timedelta(days=30)

    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:
            times = ["07:45", "20:15"]
            for time_str in times:
                event_time = tz.localize(datetime.combine(current_date.date(), datetime.strptime(time_str, "%H:%M").time()))
                event_end_time = event_time + timedelta(minutes=15)

                summary = "Confirm Scheduled Tasks 💙 TimeFinder" if time_str == "07:45" else "Check TimeFinder"
                description_url = "http://localhost:3000/googleconnect"
                description = f"Click [here]({description_url}) to visit TimeFinder and manage your tasks!"

                event_details = {
                    'summary': summary,
                    'description': description,
                    'start': {'dateTime': event_time.isoformat()},
                    'end': {'dateTime': event_end_time.isoformat()},
                    'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 15}]}
                }

                if not event_already_scheduled(access_token, calendar_id, event_time, event_end_time):
                    response = create_calendar_event(access_token, calendar_id, event_details)
                    responses.append(response)

        current_date += timedelta(days=1)

    return responses


def event_already_scheduled(access_token, calendar_id, start_time, end_time):
    time_min = start_time.isoformat()
    time_max = end_time.isoformat()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True
    }
    url = f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/{calendar_id}/events"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        events = response.json().get('items', [])
        for event in events:
            if event['start']['dateTime'] == time_min and event['end']['dateTime'] == time_max:
                return True
    return False