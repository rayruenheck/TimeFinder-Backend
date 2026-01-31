from flask import Flask
import os
from dotenv import load_dotenv
from flask_cors import CORS
from flask_pymongo import PyMongo

load_dotenv()

def create_app():
    app = Flask(__name__)

    # MongoDB configuration
    app.config["MONGO_URI"] = os.getenv("MONGODB_URI")
    app.secret_key = os.getenv("SECRET_KEY")

    # CORS configuration - allows frontend to make requests
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    CORS(app, origins=[frontend_url], supports_credentials=True)

    # Debug mode - only enabled in development
    app.config['DEBUG'] = os.getenv('FLASK_ENV') != 'production'

    # Initialize MongoDB
    mongo = PyMongo(app)

    # Register blueprints
    from .users_routes import users_bp
    from .tasks_routes import tasks_bp
    from .schedule_routes import schedule_bp
    from .health_routes import health_bp

    app.register_blueprint(users_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(health_bp)

    return app
