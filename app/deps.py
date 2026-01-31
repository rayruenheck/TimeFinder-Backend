import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from .repositories import UserRepository, TaskRepository
from .calendar_client import GoogleCalendarClient
from .scheduler import Scheduler

load_dotenv()

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["timefinder"]

GOOGLE_CALENDAR_API_BASE_URL = os.getenv("GOOGLE_CALENDAR_API_BASE_URL")

calendar_client = GoogleCalendarClient(GOOGLE_CALENDAR_API_BASE_URL)

users_collection = db.users
tasks_collection = db.tasks

user_repo = UserRepository(users_collection)
task_repo = TaskRepository(tasks_collection)

scheduler = Scheduler(calendar_client, user_repo)