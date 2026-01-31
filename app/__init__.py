from flask import Flask
import os
from dotenv import load_dotenv
from flask_cors import CORS
from flask_pymongo import PyMongo
from app.auth.users import users_bp


load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.getenv("MONGODB_URI")
app.secret_key = os.getenv("SECRET_KEY")

# CORS configuration - allows frontend to make requests
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS(app, origins=[frontend_url], supports_credentials=True)

# Debug mode - only enabled in development
app.config['DEBUG'] = os.getenv('FLASK_ENV') != 'production'

mongo = PyMongo(app)

app.register_blueprint(users_bp)


if __name__ == '__main__':
    app.run(debug=True)