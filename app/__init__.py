from flask import Flask


def create_app():
    app = Flask(__name__)

    from .users_routes import users_bp
    from .tasks_routes import tasks_bp
    from .schedule_routes import schedule_bp
    from .health_routes import health_bp

    # Register blueprints
    app.register_blueprint(users_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(health_bp)

    return app
