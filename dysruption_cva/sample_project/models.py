"""
Database Models for Task Management API
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    """
    User model for authentication and authorization.

    Attributes:
        id: Unique user identifier
        email: User's email address (unique)
        password_hash: Bcrypt hashed password
        created_at: Account creation timestamp
        tasks: Related tasks for this user
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to tasks
    tasks = db.relationship("Task", backref="owner", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"

    def to_dict(self):
        """Convert user to dictionary (excluding password)."""
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Task(db.Model):
    """
    Task model for todo items.

    Attributes:
        id: Unique task identifier
        user_id: Foreign key to owning user
        title: Task title (required, max 100 chars)
        description: Task description (optional, max 500 chars)
        completed: Whether task is completed
        created_at: Task creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), default="")
    completed = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Task {self.id}: {self.title[:20]}>"

    def to_dict(self):
        """Convert task to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def get_user_tasks(cls, user_id, completed=None, page=1, per_page=20):
        """
        Get paginated tasks for a user.

        Args:
            user_id: The user's ID
            completed: Filter by completion status (optional)
            page: Page number (default 1)
            per_page: Items per page (default 20)

        Returns:
            Pagination object with tasks
        """
        query = cls.query.filter_by(user_id=user_id)

        if completed is not None:
            query = query.filter_by(completed=completed)

        return query.order_by(cls.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
