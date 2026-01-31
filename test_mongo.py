import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# Load environment variables
load_dotenv()

uri = os.getenv("MONGODB_URI")

if not uri:
    print("❌ ERROR: MONGODB_URI not found in .env file")
    exit(1)

print(f"📡 Testing MongoDB connection...")
print(f"🔗 Connection string: {uri[:30]}...{uri[-20:]}")

try:
    # Create a new client and connect to the server
    client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=5000)

    # Send a ping to confirm a successful connection
    client.admin.command('ping')

    print("✅ SUCCESS: Connected to MongoDB Atlas!")

    # Get database info
    db = client["timefinder"]
    print(f"📊 Database: {db.name}")

    # List collections
    collections = db.list_collection_names()
    print(f"📁 Collections: {collections if collections else 'No collections yet'}")

    client.close()

except Exception as e:
    print(f"❌ ERROR: Failed to connect to MongoDB")
    print(f"Details: {str(e)}")
    exit(1)
