from flask import Flask
import os
from dotenv import load_dotenv
from flask_cors import CORS
from flask_pymongo import PyMongo
from app.auth.users import users_bp
from flask_jwt_extended import JWTManager

load_dotenv()

app = Flask(__name__)
app.config["MONGO_URI"] = os.environ.get('MONGO_URI')


app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')

CORS(app, supports_credentials=True)

jwt = JWTManager(app)
mongo = PyMongo(app)

app.register_blueprint(users_bp)


if __name__ == '__main__':
    app.run(debug=True)