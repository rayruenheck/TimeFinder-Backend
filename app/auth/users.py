from flask import request, jsonify, session
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

def find_optimal_slots(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    today = datetime.datetime.now().strftime('%Y-%m-%d')
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
    # Assume working hours from 9 AM to 5 PM
    start_of_day = datetime.datetime.strptime(f"{today} 09:00", '%Y-%m-%d %H:%M')
    end_of_day = datetime.datetime.strptime(f"{today} 17:00", '%Y-%m-%d %H:%M')
    slots = [(start_of_day, end_of_day)]

    for event in events:
        start = datetime.datetime.fromisoformat(event['start']['dateTime'][:-1])
        end = datetime.datetime.fromisoformat(event['end']['dateTime'][:-1])
        new_slots = []
        for slot_start, slot_end in slots:
            if start > slot_end or end < slot_start:
                # No overlap
                new_slots.append((slot_start, slot_end))
            else:
                # Adjust current slot based on the event time
                if slot_start < start:
                    new_slots.append((slot_start, start))
                if slot_end > end:
                    new_slots.append((end, slot_end))
        slots = new_slots

    # Convert datetime slots to string for better readability
    available_slots = [(slot[0].time().strftime('%H:%M'), slot[1].time().strftime('%H:%M')) for slot in slots if slot[0] != slot[1]]
    return available_slots