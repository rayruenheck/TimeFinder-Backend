from flask import request, jsonify, session
import requests
from datetime import datetime
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

# def get_user_info(userId):
#     user = users_collection.find_one({'idToken' : userId})

#     if not user:
#         print('user not found')
#     else:
#        return user

# def get_user_task(userId):
   
#     today_date = datetime.now().strftime("%Y-%m-%d")
    
    
#     tasks = tasks_collection.find_one({"userId": userId, "date": today_date})

#     if tasks:
#         return tasks
#     else:
#         print('No tasks found for user on today\'s date.')
#         return None


# def find_optimal_slots(access_token, tasks):
#     """Analyze Google Calendar to find optimal slots for tasks."""
#     headers = {'Authorization': f'Bearer {access_token}'}
#     # Example: Query the calendar for events on the current day
#     today = datetime.now().strftime("%Y-%m-%d")
#     params = {
#         'timeMin': f'{today}T00:00:00Z',
#         'timeMax': f'{today}T23:59:59Z',
#         'singleEvents': 'true',
#         'orderBy': 'startTime',
#     }
#     response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers=headers, params=params)
#     events = response.json().get('items', [])
#     # Logic to find optimal slots based on events and tasks
#     return events



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
    

@users_bp.post('/schedule_tasks')
def schedule_tasks():
    user_id = session.get("userId")
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400

    user = users_collection.find_one({'idToken': user_id})
    if not user:
        return jsonify({'error': 'User not found'}), 404

    today_date = datetime.now().strftime("%Y-%m-%d")
    tasks = tasks_collection.find_one({"userId": user_id, "date": today_date})
    if not tasks:
        return jsonify({'error': 'No tasks found for today'}), 404

    access_token = user.get('accessToken')
    if not access_token:
        return jsonify({'error': 'Access token is missing'}), 400

    
    return find_optimal_slots_and_schedule_tasks(access_token, tasks)


def find_optimal_slots_and_schedule_tasks(access_token, tasks):
    """Connect to Google Calendar API, find optimal time slots, and schedule tasks."""
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {
        'timeMin': f'{datetime.now().strftime("%Y-%m-%d")}T00:00:00Z',
        'timeMax': f'{datetime.now().strftime("%Y-%m-%d")}T23:59:59Z',
        'singleEvents': True,
        'orderBy': 'startTime'
    }
    response = requests.get(f"{GOOGLE_CALENDAR_API_BASE_URL}/calendars/primary/events", headers=headers, params=params)
    events = response.json().get('items', [])

    # Add logic to find optimal slots based on events and tasks logic
    # For example, check for free slots according to task priorities and user concentration times

    # Dummy logic for inserting tasks into the calendar (to be replaced with actual logic)
    scheduled_events = []  # This would be your list of scheduled tasks
    for task in tasks['tasks']:  # Assuming tasks are stored in a 'tasks' key
        # This is a simplified placeholder for where you'd insert your task scheduling logic
        scheduled_events.append(task)

    return jsonify({'message': 'Tasks scheduled successfully', 'events': scheduled_events})