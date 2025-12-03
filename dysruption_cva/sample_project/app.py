"""
Sample Project: Task Management API
A simple Flask-based REST API for task management.
This project is used to test the Dysruption CVA system.
"""

import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
from functools import wraps

# Configuration
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///tasks.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Models
class User(db.Model):
    """User model for authentication."""

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship("Task", backref="owner", lazy=True)

    def set_password(self, password):
        """Hash and set password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password."""
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    """Task model for todo items."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Authentication decorator
def token_required(f):
    """Decorator to require valid JWT token."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            if token.startswith("Bearer "):
                token = token[7:]
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_user = User.query.get(data["user_id"])
            if not current_user:
                return jsonify({"error": "User not found"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(current_user, *args, **kwargs)

    return decorated


# Validation helpers
def validate_email(email):
    """Validate email format."""
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain a number"
    return True, None


# Auth routes
@app.route("/auth/register", methods=["POST"])
def register():
    """Register a new user."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        email = data.get("email", "").strip()
        password = data.get("password", "")

        # Validate email
        if not email or not validate_email(email):
            return jsonify({"error": "Invalid email format"}), 400

        # Validate password
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        # Check if user exists
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 400

        # Create user
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return jsonify({"message": "User registered successfully", "user_id": user.id}), 201

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Registration error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/auth/login", methods=["POST"])
def login():
    """Login and get JWT token."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        email = data.get("email", "").strip()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid credentials"}), 401

        # Generate token (24 hour expiry)
        token = jwt.encode(
            {"user_id": user.id, "exp": datetime.utcnow() + timedelta(hours=24)},
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )

        return jsonify({"token": token}), 200

    except Exception as e:
        app.logger.error(f"Login error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Task routes
@app.route("/tasks", methods=["GET"])
@token_required
def get_tasks(current_user):
    """Get all tasks for current user."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        per_page = min(per_page, 100)  # Limit max per page

        tasks = (
            Task.query.filter_by(user_id=current_user.id)
            .order_by(Task.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        return (
            jsonify(
                {
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "description": t.description,
                            "completed": t.completed,
                            "created_at": t.created_at.isoformat(),
                            "updated_at": t.updated_at.isoformat(),
                        }
                        for t in tasks.items
                    ],
                    "total": tasks.total,
                    "page": page,
                    "pages": tasks.pages,
                }
            ),
            200,
        )

    except Exception as e:
        app.logger.error(f"Get tasks error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/tasks", methods=["POST"])
@token_required
def create_task(current_user):
    """Create a new task."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        title = data.get("title", "").strip()
        description = data.get("description", "").strip()

        # Validate title
        if not title:
            return jsonify({"error": "Title is required"}), 400
        if len(title) > 100:
            return jsonify({"error": "Title must be 100 characters or less"}), 400

        # Validate description
        if len(description) > 500:
            return jsonify({"error": "Description must be 500 characters or less"}), 400

        task = Task(user_id=current_user.id, title=title, description=description)
        db.session.add(task)
        db.session.commit()

        return (
            jsonify(
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "completed": task.completed,
                    "created_at": task.created_at.isoformat(),
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Create task error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/tasks/<int:task_id>", methods=["GET"])
@token_required
def get_task(current_user, task_id):
    """Get a specific task."""
    try:
        task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()

        if not task:
            return jsonify({"error": "Task not found"}), 404

        return (
            jsonify(
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "completed": task.completed,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                }
            ),
            200,
        )

    except Exception as e:
        app.logger.error(f"Get task error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/tasks/<int:task_id>", methods=["PUT"])
@token_required
def update_task(current_user, task_id):
    """Update a task."""
    try:
        task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()

        if not task:
            return jsonify({"error": "Task not found"}), 404

        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Update fields if provided
        if "title" in data:
            title = data["title"].strip()
            if not title:
                return jsonify({"error": "Title cannot be empty"}), 400
            if len(title) > 100:
                return jsonify({"error": "Title must be 100 characters or less"}), 400
            task.title = title

        if "description" in data:
            description = data["description"].strip()
            if len(description) > 500:
                return jsonify({"error": "Description must be 500 characters or less"}), 400
            task.description = description

        if "completed" in data:
            task.completed = bool(data["completed"])

        db.session.commit()

        return (
            jsonify(
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "completed": task.completed,
                    "updated_at": task.updated_at.isoformat(),
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Update task error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
@token_required
def delete_task(current_user, task_id):
    """Delete a task."""
    try:
        task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()

        if not task:
            return jsonify({"error": "Task not found"}), 404

        db.session.delete(task)
        db.session.commit()

        return jsonify({"message": "Task deleted"}), 200

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Delete task error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return jsonify({"error": "Internal server error"}), 500


# Initialize database
def init_db():
    """Initialize the database."""
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
