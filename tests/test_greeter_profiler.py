"""
Unit tests for the GreeterProfiler agent.
"""

import unittest
import sqlite3

# Import the functions and classes we need to test
from aduro_agents.greeter_profiler import (
    GreeterProfiler,
    _update_user_profile,
    _get_user_profile_from_db,
    get_missing_fields
)

class TestGreeterProfiler(unittest.IsolatedAsyncioTestCase):
    """Test cases for the GreeterProfiler agent."""

    async def asyncSetUp(self):
        """Set up test database and agent."""
        # Create in-memory database for testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                city TEXT,
                email TEXT UNIQUE,
                date_of_birth DATE,
                dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
                medical_conditions TEXT,
                physical_limitations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert test user with complete profile
        self.conn.execute("""
            INSERT INTO users (id, first_name, last_name, city, email, date_of_birth, dietary_preference)
            VALUES (1, 'Test', 'User', 'Test City', 'test@example.com', '1990-01-01', 'vegetarian')
        """)
        self.conn.commit()
        
        # Create agent instance
        self.agent = GreeterProfiler()
    
    async def asyncTearDown(self):
        """Clean up test database."""
        self.conn.close()
    
    async def test_complete_profile(self):
        """Test interaction with a complete profile."""
        response = await self.agent.process_input(
            "Hello",
            {"user_id": 1},
            test_conn=self.conn
        )
        self.assertIn("Your profile is complete", response)
    
    async def test_missing_user_id(self):
        """Test handling of missing user ID."""
        with self.assertRaises(ValueError):
            await self.agent.process_input("Hi", {})
    
    async def test_incomplete_profile_flow(self):
        """Test the complete flow for a user with an incomplete profile."""
        # Create a new user with minimal information
        self.conn.execute("""
            INSERT INTO users (id, first_name, email)
            VALUES (2, 'Incomplete', 'incomplete@example.com')
        """)
        self.conn.commit()
        
        # First interaction should ask for last name
        response = await self.agent.process_input(
            "Hi",
            {"user_id": 2},
            test_conn=self.conn
        )
        self.assertIn("last name", response.lower())
        
        # Provide last name, should now ask for city
        response = await self.agent.process_input(
            "User",
            {"user_id": 2},
            test_conn=self.conn
        )
        self.assertIn("city", response.lower())
        
        # Provide city, should ask for date of birth
        response = await self.agent.process_input(
            "Test City",
            {"user_id": 2},
            test_conn=self.conn
        )
        self.assertIn("date of birth", response.lower())
        
        # Provide date of birth, should ask for dietary preference
        response = await self.agent.process_input(
            "1990-01-01",
            {"user_id": 2},
            test_conn=self.conn
        )
        self.assertIn("dietary preference", response.lower())
        
        # Provide dietary preference, profile should now be complete
        response = await self.agent.process_input(
            "vegetarian",
            {"user_id": 2},
            test_conn=self.conn
        )
        self.assertIn("profile is complete", response.lower())
        
        # Verify all required fields are now in the database
        profile = await _get_user_profile_from_db(2, test_conn=self.conn)
        self.assertEqual(profile["first_name"], "Incomplete")
        self.assertEqual(profile["last_name"], "User")
        self.assertEqual(profile["city"], "Test City")
        self.assertEqual(profile["date_of_birth"], "1990-01-01")
        self.assertEqual(profile["dietary_preference"], "vegetarian")


class TestHelperFunctions(unittest.IsolatedAsyncioTestCase):
    """Test cases for helper functions."""
    
    async def asyncSetUp(self):
        """Set up test database."""
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                city TEXT,
                email TEXT UNIQUE,
                date_of_birth DATE,
                dietary_preference TEXT,
                medical_conditions TEXT,
                physical_limitations TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
    async def asyncTearDown(self):
        """Clean up test database."""
        self.conn.close()
    
    async def test_update_user_profile(self):
        """Test updating a user profile."""
        # Insert a test user
        self.conn.execute("""
            INSERT INTO users (id, first_name, email)
            VALUES (1, 'Test', 'test@example.com')
        """)
        self.conn.commit()
        
        # Update the user's profile
        updates = {
            "first_name": "Updated",
            "last_name": "User",
            "city": "Test City"
        }
        
        result = await _update_user_profile(1, updates, test_conn=self.conn)
        self.assertTrue(result)
        
        # Verify the updates
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = 1")
        user = cursor.fetchone()
        
        self.assertEqual(user["first_name"], "Updated")
        self.assertEqual(user["last_name"], "User")
        self.assertEqual(user["city"], "Test City")
    
    async def test_get_user_profile(self):
        """Test retrieving a user profile."""
        # Insert a test user with some data
        self.conn.execute("""
            INSERT INTO users (id, first_name, last_name, email, city)
            VALUES (1, 'Test', 'User', 'test@example.com', 'Test City')
        """)
        self.conn.commit()
        
        # Get the profile
        profile = await _get_user_profile_from_db(1, test_conn=self.conn)
        
        # Verify the profile data
        self.assertEqual(profile["first_name"], "Test")
        self.assertEqual(profile["last_name"], "User")
        self.assertEqual(profile["city"], "Test City")
    
    def test_get_missing_fields(self):
        """Test identification of missing required fields."""
        # Test with all required fields present
        complete_profile = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "city": "Test City",
            "date_of_birth": "1990-01-01",
            "dietary_preference": "vegetarian"
        }
        missing = get_missing_fields(complete_profile)
        self.assertEqual(len(missing), 0)
        
        # Test with missing required fields
        incomplete_profile = {
            "first_name": "Test",
            "email": "test@example.com"
        }
        missing = get_missing_fields(incomplete_profile)
        self.assertIn("last_name", missing)
        self.assertIn("city", missing)
        self.assertIn("date_of_birth", missing)
        self.assertIn("dietary_preference", missing)
        self.assertEqual(len(missing), 4)


if __name__ == "__main__":
    unittest.main()
