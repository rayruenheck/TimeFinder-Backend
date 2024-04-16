from flask import Flask
import os
from dotenv import load_dotenv
from flask_cors import CORS
from flask_pymongo import PyMongo
from app.auth.users import users_bp


load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.environ.get('MONGO_URI')



CORS(app, supports_credentials=True)


mongo = PyMongo(app)

app.register_blueprint(users_bp)


if __name__ == '__main__':
    app.run(debug=True)