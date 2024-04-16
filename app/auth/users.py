from flask import request, jsonify
from . import users_bp
from pymongo import MongoClient, ReturnDocument
from pymongo.server_api import ServerApi
import os

uri = os.getenv('MONGO_URI')
client = MongoClient(uri, server_api=ServerApi('1'))
mongo = client.TimeFinder

@users_bp.route('/users', methods=['POST'])
def create_or_update_user():
    user_data = request.get_json()
    
    # Check if user_data is valid and contains an email
    if not user_data or 'email' not in user_data:
        return jsonify(message="Missing required user data"), 400

    email = user_data['email']
    
    # Perform an upsert operation
    result = mongo.users.update_one(
        {"email": email},  # Query part: what to find
        {"$set": user_data},  # Update part: what to change or add
        upsert=True  # Upsert option set to True
    )
    
    # Check the result of the upsert operation
    if result.matched_count > 0:
        return jsonify(message="User updated successfully"), 200
    elif result.upserted_id is not None:
        return jsonify(message="User created successfully"), 201
    else:
        return jsonify(message="User not created or updated"), 500