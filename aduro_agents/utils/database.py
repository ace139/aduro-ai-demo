"""
Database Manager for Aduro AI Health Assistant.

This module provides a centralized interface for all database operations,
ensuring consistent error handling, connection management, and data validation.
"""

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type aliases
UserID = int
CGMReading = dict[str, float | str | datetime]
UserProfile = dict[str, Any]

class DatabaseManager:
    """
    Centralized database management for the Aduro AI Health Assistant.

    This class provides methods for all database operations, including:
    - User profile management
    - CGM readings management
    - Database schema management
    - Connection handling
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> Any:
        """
        Return a pydantic-core schema for the DatabaseManager class.
        This tells Pydantic to treat DatabaseManager as an arbitrary type.
        """
        from pydantic_core import core_schema
        return core_schema.any_schema()

    def __init__(self, db_path: str | None = None):
        """
        Initialize the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file. If None, uses the default path.
        """
        self.db_path = db_path or os.getenv('DB_PATH', 'db/users.db')
        self._ensure_db_directory()
        self._init_db()

    def _ensure_db_directory(self) -> None:
        """Ensure the database directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for database connections.

        Yields:
            sqlite3.Connection: A database connection

        Raises:
            sqlite3.Error: If there's an error connecting to the database
        """
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys = ON')
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def _init_db(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create users table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                city TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                date_of_birth DATE NOT NULL,
                dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
                medical_conditions TEXT,
                physical_limitations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Create cgm_readings table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cgm_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reading REAL NOT NULL,
                reading_type TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """)

            # Create indexes for better query performance
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cgm_readings_user_id
            ON cgm_readings(user_id)
            """)

            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cgm_readings_timestamp
            ON cgm_readings(timestamp)
            """)

            conn.commit()

    # User Profile Methods

    async def get_user_profile(self, user_id: UserID) -> UserProfile | None:
        """
        Retrieve a user's profile.

        Args:
            user_id: The ID of the user

        Returns:
            Optional[Dict]: The user's profile data if found, None otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, first_name, last_name, city, email,
                           date_of_birth, dietary_preference, medical_conditions,
                           physical_limitations, created_at, updated_at
                    FROM users
                    WHERE id = ?
                """, (user_id,))

                row = cursor.fetchone()
                if not row:
                    return None

                return dict(row)

        except sqlite3.Error as e:
            logger.error(f"Error getting user profile for user {user_id}: {e}")
            raise

    async def create_user_profile(self, profile_data: UserProfile) -> UserID:
        """
        Create a new user profile.

        Args:
            profile_data: Dictionary containing user profile data
                Required keys: first_name, last_name, city, email, date_of_birth
                Optional keys: dietary_preference, medical_conditions, physical_limitations

        Returns:
            int: The ID of the newly created user

        Raises:
            ValueError: If required fields are missing
            sqlite3.IntegrityError: If a user with the email already exists
        """
        required_fields = ['first_name', 'last_name', 'city', 'email', 'date_of_birth']
        missing = [field for field in required_fields if field not in profile_data or not profile_data[field]]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (
                        first_name, last_name, city, email, date_of_birth,
                        dietary_preference, medical_conditions, physical_limitations
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    profile_data['first_name'],
                    profile_data['last_name'],
                    profile_data['city'],
                    profile_data['email'],
                    profile_data['date_of_birth'],
                    profile_data.get('dietary_preference'),
                    profile_data.get('medical_conditions'),
                    profile_data.get('physical_limitations')
                ))

                user_id = cursor.lastrowid
                conn.commit()
                return user_id

        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: users.email" in str(e):
                raise ValueError(f"A user with email {profile_data['email']} already exists") from e
            raise
        except sqlite3.Error as e:
            logger.error(f"Error creating user profile: {e}")
            raise

    async def update_user_profile(self, user_id: UserID, updates: dict[str, Any]) -> bool:
        """
        Update a user's profile.

        Args:
            user_id: The ID of the user to update
            updates: Dictionary of fields to update

        Returns:
            bool: True if the update was successful, False otherwise
        """
        if not updates:
            return False

        # Filter out None values and create set expressions
        valid_updates = {k: v for k, v in updates.items() if v is not None}
        if not valid_updates:
            return False

        set_clause = ", ".join(f"{field} = ?" for field in valid_updates)
        values = list(valid_updates.values())
        values.append(user_id)  # For the WHERE clause

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    values
                )

                updated = cursor.rowcount > 0
                if updated:
                    conn.commit()
                return updated

        except sqlite3.Error as e:
            logger.error(f"Error updating profile for user {user_id}: {e}")
            raise

    async def update_user_profile_field(self, user_id: UserID, field_name: str, value: Any) -> bool:
        """
        Update a single field in a user's profile.

        Args:
            user_id: The ID of the user
            field_name: The name of the field to update
            value: The new value for the field

        Returns:
            bool: True if the update was successful, False otherwise
        """
        valid_fields = [
            'first_name', 'last_name', 'city', 'email', 'date_of_birth',
            'dietary_preference', 'medical_conditions', 'physical_limitations'
        ]

        if field_name not in valid_fields:
            raise ValueError(f"Invalid field name: {field_name}")

        return await self.update_user_profile(user_id, {field_name: value})

    async def is_profile_complete(self, user_id: UserID) -> bool:
        """
        Check if a user's profile is complete.

        A profile is considered complete if all required fields are filled.

        Args:
            user_id: The ID of the user

        Returns:
            bool: True if the profile is complete, False otherwise
        """

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as missing
                    FROM (
                        SELECT 1
                        FROM users
                        WHERE id = ?
                        AND (
                            first_name IS NULL OR first_name = '' OR
                            last_name IS NULL OR last_name = '' OR
                            city IS NULL OR city = '' OR
                            email IS NULL OR email = '' OR
                            date_of_birth IS NULL OR
                            dietary_preference IS NULL
                        )
                    )
                """, (user_id,))

                missing_count = cursor.fetchone()['missing']
                return missing_count == 0

        except sqlite3.Error as e:
            logger.error(f"Error checking profile completeness for user {user_id}: {e}")
            raise

    async def get_next_missing_profile_field(self, user_id: UserID) -> str | None:
        """
        Get the next missing required field for a user's profile.

        Args:
            user_id: The ID of the user

        Returns:
            Optional[str]: The name of the next missing field, or None if all required fields are complete
        """
        field_priority = [
            'first_name',
            'last_name',
            'email',
            'date_of_birth',
            'city',
            'dietary_preference'
        ]

        try:
            profile = await self.get_user_profile(user_id)
            if not profile:
                return 'first_name'  # Start with first name for new profiles

            for field in field_priority:
                if not profile.get(field):
                    return field

            return None  # All required fields are complete

        except Exception as e:
            logger.error(f"Error getting next missing field for user {user_id}: {e}")
            raise

    # CGM Reading Methods

    async def save_cgm_reading(
        self,
        user_id: UserID,
        reading: float,
        timestamp: datetime | None = None,
        reading_type: str | None = None
    ) -> int:
        """
        Save a CGM reading to the database.

        Args:
            user_id: The ID of the user
            reading: The CGM reading value
            timestamp: When the reading was taken (defaults to now)
            reading_type: Type of reading (breakfast, lunch, dinner, snack).
                        If None, it will be inferred from the timestamp.

        Returns:
            int: The ID of the inserted reading

        Raises:
            ValueError: If the reading is invalid or user doesn't exist
        """
        if not isinstance(reading, int | float) or not (0 <= reading <= 600):
            raise ValueError("Invalid reading value. Must be a number between 0 and 600.")

        if timestamp is None:
            timestamp = datetime.now()

        if reading_type is None:
            # Infer reading type from time of day
            hour = timestamp.hour
            if 5 <= hour < 11:
                reading_type = 'breakfast'
            elif 11 <= hour < 16:
                reading_type = 'lunch'
            elif 16 <= hour < 22:
                reading_type = 'dinner'
            else:
                reading_type = 'snack'

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Verify user exists
                cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
                if not cursor.fetchone():
                    raise ValueError(f"User with ID {user_id} does not exist")

                # Insert the reading
                cursor.execute("""
                    INSERT INTO cgm_readings (user_id, reading, reading_type, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (user_id, float(reading), reading_type, timestamp))

                reading_id = cursor.lastrowid
                conn.commit()
                return reading_id

        except sqlite3.Error as e:
            logger.error(f"Error saving CGM reading for user {user_id}: {e}")
            raise

    async def get_recent_cgm_readings(
        self,
        user_id: UserID,
        limit: int = 10,
        days: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent CGM readings for a user.

        Args:
            user_id: The ID of the user
            limit: Maximum number of readings to return
            days: Optional number of days to look back (if None, returns most recent readings)

        Returns:
            List[Dict]: List of CGM readings with their details
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT id, reading, reading_type, timestamp
                    FROM cgm_readings
                    WHERE user_id = ?
                """

                params = [user_id]

                if days is not None:
                    query += " AND timestamp >= datetime('now', ? || ' days')"
                    params.append(f"-{days}")

                query += " ORDER BY timestamp DESC"

                if limit > 0:
                    query += " LIMIT ?"
                    params.append(limit)

                cursor.execute(query, params)

                return [dict(row) for row in cursor.fetchall()]

        except sqlite3.Error as e:
            logger.error(f"Error retrieving CGM readings for user {user_id}: {e}")
            raise

    async def get_cgm_statistics(
        self,
        user_id: UserID,
        days: int = 30
    ) -> dict[str, Any]:
        """
        Get statistics for a user's CGM readings over a period of time.

        Args:
            user_id: The ID of the user
            days: Number of days to look back

        Returns:
            Dict: Statistics including average, min, max, and count of readings
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        COUNT(*) as count,
                        AVG(reading) as avg_reading,
                        MIN(reading) as min_reading,
                        MAX(reading) as max_reading
                    FROM cgm_readings
                    WHERE user_id = ?
                    AND timestamp >= datetime('now', ? || ' days')
                """, (user_id, f"-{days}"))

                stats = cursor.fetchone()

                return {
                    "count": stats["count"],
                    "average": round(float(stats["avg_reading"] or 0), 1),
                    "min": round(float(stats["min_reading"] or 0), 1),
                    "max": round(float(stats["max_reading"] or 0), 1),
                    "period_days": days
                }

        except sqlite3.Error as e:
            logger.error(f"Error getting CGM statistics for user {user_id}: {e}")
            raise

    # Helper Methods

    async def user_exists(self, user_id: UserID) -> bool:
        """
        Check if a user exists in the database.

        Args:
            user_id: The ID of the user to check

        Returns:
            bool: True if the user exists, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking if user {user_id} exists: {e}")
            raise

    async def get_user_id_by_email(self, email: str) -> UserID | None:
        """
        Get a user's ID by their email address.

        Args:
            email: The email address to look up

        Returns:
            Optional[int]: The user's ID if found, None otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                row = cursor.fetchone()
                return row["id"] if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting user ID for email {email}: {e}")
            raise

# Create a global instance for convenience
db = DatabaseManager()
