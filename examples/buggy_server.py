"""Example: A web service with several subtle bugs for Kagerou to find."""

import hashlib
import os
import sqlite3
import threading
from typing import Any


# BUG 1: Global mutable state shared across threads without synchronization
_cache: dict[str, Any] = {}
_cache_hits = 0


class UserService:
    """Service for managing users."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)

    # BUG 2: SQL injection vulnerability
    def get_user(self, username: str) -> dict[str, Any] | None:
        """Get a user by username."""
        if self.conn is None:
            return None
        cursor = self.conn.execute(
            f"SELECT id, username, email, role FROM users WHERE username = '{username}'"
        )
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "role": row[3]}
        return None

    # BUG 3: Password stored with weak hash (MD5) and no salt
    def create_user(self, username: str, password: str, email: str) -> int:
        """Create a new user and return user ID."""
        password_hash = hashlib.md5(password.encode()).hexdigest()

        if self.conn is None:
            self.connect()

        # BUG 4: conn could still be None after connect() if it fails silently
        cursor = self.conn.execute(  # type: ignore[union-attr]
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, password_hash, email),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # BUG 5: Resource leak - file opened but never closed on error path
    def import_users(self, csv_path: str) -> int:
        """Import users from a CSV file."""
        f = open(csv_path, "r")
        count = 0
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue  # BUG: file handle leaks on continue/exception
            username, password, email = parts[0], parts[1], parts[2]
            self.create_user(username, password, email)
            count += 1
        f.close()
        return count

    # BUG 6: Off-by-one error in pagination
    def list_users(self, page: int, page_size: int = 10) -> list[dict[str, Any]]:
        """List users with pagination."""
        if self.conn is None:
            return []
        # Off-by-one: page 1 should start at offset 0, but this starts at page_size
        offset = page * page_size
        cursor = self.conn.execute(
            "SELECT id, username, email FROM users LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        return [{"id": r[0], "username": r[1], "email": r[2]} for r in cursor.fetchall()]

    # BUG 7: TOCTOU race condition
    def delete_user_data(self, user_id: int) -> bool:
        """Delete user's uploaded files."""
        data_dir = f"/data/users/{user_id}"
        if os.path.exists(data_dir):
            # Race: directory could be removed between check and use
            for filename in os.listdir(data_dir):
                # BUG 8: Path traversal - filename not sanitized
                filepath = os.path.join(data_dir, filename)
                os.remove(filepath)
            os.rmdir(data_dir)
            return True
        return False


class SessionManager:
    """Manages user sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    # BUG 9: Predictable session token
    def create_session(self, user_id: int) -> str:
        """Create a new session for a user."""
        token = hashlib.md5(str(user_id).encode()).hexdigest()
        self.sessions[token] = {
            "user_id": user_id,
            "created": True,
        }
        return token

    # BUG 10: Logic error - checking wrong variable
    def validate_session(self, token: str) -> bool:
        """Check if a session is valid."""
        session = self.sessions.get(token)
        if token is not None:  # Should be: if session is not None
            return True
        return False

    def get_user_id(self, token: str) -> int | None:
        """Get the user ID for a session."""
        session = self.sessions.get(token)
        if session:
            return session["user_id"]
        return None


def process_payment(amount: float, currency: str) -> dict[str, Any]:
    """Process a payment.

    BUG 11: Floating point comparison for money
    BUG 12: No input validation for negative amounts
    """
    # Using float for money is a classic bug
    tax = amount * 0.1
    total = amount + tax

    if total == 110.0:  # Floating point comparison
        discount = total * 0.05
        total = total - discount

    return {
        "amount": amount,
        "tax": tax,
        "total": total,
        "currency": currency,
    }


def calculate_average(numbers: list[int]) -> float:
    """Calculate the average of a list.

    BUG 13: Division by zero when list is empty
    """
    total = sum(numbers)
    return total / len(numbers)
