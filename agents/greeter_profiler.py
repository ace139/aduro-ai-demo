"""
Greeter Profiler Agent for collecting and validating user profile information.
"""

from typing import Dict, List, Any
import sqlite3
from pathlib import Path
import unittest

from agents import Agent, function_tool

# Constants
DB_PATH = Path("db/users.db")

async def _update_user_profile(user_id: int, updates: Dict[str, Any], test_conn=None) -> bool:
    """
    Update user profile in the database.
    
    Args:
        user_id: The ID of the user
        updates: Dictionary of fields to update
        test_conn: Optional database connection for testing
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    if not updates:
        return False
        
    close_conn = False
    if test_conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_conn = True
    else:
        conn = test_conn
    
    try:
        cursor = conn.cursor()
        
        # Build the SET clause dynamically based on provided updates
        set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
        values = list(updates.values())
        values.append(user_id)  # For the WHERE clause
        
        query = f"""
            UPDATE users 
            SET {set_clause}
            WHERE id = ?
        """
        
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating user profile: {e}")
        if close_conn:
            conn.rollback()
        return False
    finally:
        if close_conn:
            conn.close()

async def _get_user_profile_from_db(user_id: int, test_conn=None) -> Dict[str, Any]:
    """
    Internal function to fetch user profile from the database.
    
    Args:
        user_id: The ID of the user
        test_conn: Optional database connection for testing
        
    Returns:
        Dictionary containing user profile information.
    """
    close_conn = False
    if test_conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_conn = True
    else:
        conn = test_conn
        
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_name, last_name, city, email, date_of_birth,
                   dietary_preference, medical_conditions, physical_limitations
            FROM users 
            WHERE id = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        if not result:
            return {}
            
        # Convert to dict and handle None values
        profile = {k: v for k, v in dict(result).items() if v is not None}
        return profile
    finally:
        if close_conn:
            conn.close()

@function_tool
async def get_user_profile(user_id: int) -> Dict[str, Any]:
    """
    Fetches the user profile from the database.
    
    Args:
        user_id: The ID of the user
        
    Returns:
        Dictionary containing user profile information with the following fields:
        {
            "first_name": str or None,
            "last_name": str or None,
            "city": str or None,
            "email": str or None,
            "date_of_birth": str or None (YYYY-MM-DD),
            "dietary_preference": str or None,
            "medical_conditions": str or None,
            "physical_limitations": str or None
        }
    """
    return await _get_user_profile_from_db(user_id)

def get_missing_fields(profile: Dict[str, Any]) -> List[str]:
    """
    Identifies which required fields are missing from the user profile.
    
    Args:
        profile: Dictionary containing user profile data
        
    Returns:
        List of missing required field names
    """
    REQUIRED_FIELDS = [
        "first_name", "last_name", "city", 
        "email", "date_of_birth", "dietary_preference"
    ]
    return [field for field in REQUIRED_FIELDS if not profile.get(field) or profile[field] == '']

class GreeterProfiler(Agent):
    """Agent responsible for greeting users and collecting profile information."""
    
    def __init__(self):
        super().__init__(
            name="greeter_profiler",
            instructions="""
            You are a friendly assistant that helps collect user profile information.
            Greet the user warmly and guide them through providing any missing details.
            Be polite, concise, and professional in your interactions.
            """,
            tools=[get_user_profile]
        )
        self._greeted_users = set()

    async def process_input(
        self, 
        user_input: str, 
        context: Dict[str, Any], 
        test_conn=None
    ) -> str:
        """
        Process user input and return a response.
        
        Args:
            user_input: The user's input text
            context: Dictionary containing additional context (e.g., user_id)
            test_conn: Optional database connection for testing
            
        Returns:
            str: The agent's response
        """
        user_id = context.get("user_id")
        if not isinstance(user_id, int) or user_id <= 0:
            return "⚠️ Missing or invalid user ID. Please re-authenticate."
        
        # Get user profile
        try:
            # Use the internal function to get the profile
            profile = await _get_user_profile_from_db(user_id, test_conn=test_conn)
            if not isinstance(profile, dict):
                profile = {}
        except Exception as e:
            print(f"Error getting user profile: {e}")
            profile = {}
        
        # Check if this is the first interaction
        is_first_interaction = user_id not in self._greeted_users
        
        if is_first_interaction:
            self._greeted_users.add(user_id)
            greeting = f"Hello {profile.get('first_name', 'there')}! 👋 I'm here to help you get started with your personalized health assistant. "
        else:
            greeting = ""
        
        # Check if the user is providing information
        if user_input and user_input.strip() and user_input.lower() not in ["hi", "hello", "hey"]:
            # Try to determine what field this might be
            missing_fields = get_missing_fields(profile)
            if missing_fields:
                field = missing_fields[0]
                
                # Map the input to a field value
                updates = {}
                if field == "dietary_preference":
                    pref = user_input.strip().lower()
                    if pref in ["vegetarian", "non-vegetarian", "vegan"]:
                        updates["dietary_preference"] = pref
                elif field == "first_name":
                    updates["first_name"] = user_input.strip()
                elif field == "last_name":
                    updates["last_name"] = user_input.strip()
                elif field == "email" and "@" in user_input:
                    updates["email"] = user_input.strip()
                elif field == "date_of_birth" and "-" in user_input:
                    updates["date_of_birth"] = user_input.strip()
                elif field == "city":
                    updates["city"] = user_input.strip()
                
                # Save the updates if any
                if updates:
                    success = await _update_user_profile(user_id, updates, test_conn=test_conn)
                    if success:
                        # Refresh the profile
                        profile = await _get_user_profile_from_db(user_id, test_conn=test_conn)
                        
        # Check for missing required fields
        missing_fields = get_missing_fields(profile)
        if missing_fields:
            if is_first_interaction:
                response = greeting + "I'll need just a few details to create a custom diet and CGM-based plan for you. Let's get started. "
            else:
                response = "Thanks! I'll update your profile with that information. "
                
            # Ask for the first missing field
            field = missing_fields[0]
            if field == "first_name":
                response += "What's your first name?"
            elif field == "last_name":
                response += "What's your last name?"
            elif field == "email":
                response += "What's your email address?"
            elif field == "date_of_birth":
                response += "What's your date of birth? (YYYY-MM-DD)"
            elif field == "dietary_preference":
                response += "What's your dietary preference? (vegetarian / non-vegetarian / vegan)"
            else:
                # For any other fields, use a generic prompt
                field_name = field.replace("_", " ")
                response += f"What's your {field_name}?"
                
            return response
        
        # If we get here, the profile is complete
        if is_first_interaction:
            return greeting + "🎉 Your profile is complete. You're all set! Let me know if you'd like to update anything."
        else:
            return "🎉 Your profile is complete. You're all set! Let me know if you'd like to update anything."


# Unit Tests
class TestGreeterProfiler(unittest.IsolatedAsyncioTestCase):
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
        
        # Insert test user
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
        """Test with a complete profile."""
        response = await self.agent.process_input(
            "Hello",
            {"user_id": 1}
        )
        self.assertIn("Your profile is complete", response)
    
    async def test_missing_user_id(self):
        """Test with missing user ID."""
        response = await self.agent.process_input("Hi", {})
        self.assertIn("Missing or invalid user ID", response)
    
    async def test_incomplete_profile(self):
        """Test with an incomplete profile."""
        # Clear any existing test data
        self.conn.execute("DELETE FROM users WHERE id = 2")
        
        # Insert user with only first_name and email (missing other required fields)
        self.conn.execute("""
            INSERT INTO users (id, first_name, email)
            VALUES (2, 'Incomplete', 'incomplete@example.com')
        """)
        self.conn.commit()
        
        # Debug: Check what's actually in the database
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = 2")
        db_user = cursor.fetchone()
        print("\nDebug - User in database:", dict(db_user) if db_user else "No user found")
        
        # Get the profile directly to check missing fields
        profile = await _get_user_profile_from_db(2, test_conn=self.conn)
        print("Debug - Profile from DB:", profile)
        missing_fields = get_missing_fields(profile)
        print("Debug - Missing fields:", missing_fields)
        
        # First interaction should ask for the first missing field (last_name)
        response = await self.agent.process_input(
            "Hi",
            {"user_id": 2},
            test_conn=self.conn
        )
        print("Debug - First response:", response)
        self.assertIn("last name", response.lower())
        
        # Simulate user providing last name
        response = await self.agent.process_input(
            "User",
            {"user_id": 2},
            test_conn=self.conn
        )
        print("Debug - After providing last name:", response)
        
        # The agent should now ask for the next missing field (city)
        self.assertIn("city", response.lower())
        
        # Simulate user providing city
        response = await self.agent.process_input(
            "Test City",
            {"user_id": 2},
            test_conn=self.conn
        )
        print("Debug - After providing city:", response)
        
        # The agent should now ask for date of birth
        self.assertIn("date of birth", response.lower())
        
        # Simulate user providing date of birth
        response = await self.agent.process_input(
            "1990-01-01",
            {"user_id": 2},
            test_conn=self.conn
        )
        print("Debug - After providing date of birth:", response)
        
        # The agent should now ask for dietary preference
        self.assertIn("dietary preference", response.lower())
        
        # Simulate user providing dietary preference
        response = await self.agent.process_input(
            "vegetarian",
            {"user_id": 2},
            test_conn=self.conn
        )
        print("Debug - After providing dietary preference:", response)
        
        # Now the profile should be complete
        updated_profile = await _get_user_profile_from_db(2, test_conn=self.conn)
        print("Debug - Final profile:", updated_profile)
        
        # Verify all required fields are present
        missing_fields = get_missing_fields(updated_profile)
        self.assertEqual(len(missing_fields), 0, f"Profile is still missing fields: {missing_fields}")

async def main():
    """Example usage of the GreeterProfiler agent."""
    # Create an in-memory database for testing
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    # Create the users table if it doesn't exist
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        city TEXT,
        email TEXT UNIQUE,
        date_of_birth TEXT,
        dietary_preference TEXT,
        medical_conditions TEXT,
        physical_limitations TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    
    # Add a test user with minimal information
    cursor.execute("""
    INSERT OR REPLACE INTO users (id, first_name, email)
    VALUES (100, 'Test', 'test@example.com')
    """)
    conn.commit()
    
    agent = GreeterProfiler()
    
    # Example 1: First interaction with a new user
    print("\n=== First Interaction ===")
    response = await agent.process_input("Hi", {"user_id": 100}, test_conn=conn)
    print(f"Agent: {response}")
    
    # Simulate user providing last name
    print("\n=== Providing Last Name ===")
    response = await agent.process_input("User", {"user_id": 100}, test_conn=conn)
    print(f"Agent: {response}")
    
    # Simulate user providing city
    print("\n=== Providing City ===")
    response = await agent.process_input("San Francisco", {"user_id": 100}, test_conn=conn)
    print(f"Agent: {response}")
    
    # Simulate user providing date of birth
    print("\n=== Providing Date of Birth ===")
    response = await agent.process_input("1990-01-01", {"user_id": 100}, test_conn=conn)
    print(f"Agent: {response}")
    
    # Simulate user providing dietary preference
    print("\n=== Providing Dietary Preference ===")
    response = await agent.process_input("vegetarian", {"user_id": 100}, test_conn=conn)
    print(f"Agent: {response}")
    
    # Show final profile
    print("\n=== Final Profile ===")
    cursor.execute("SELECT * FROM users WHERE id = 100")
    user = cursor.fetchone()
    print("User profile:", dict(user) if user else "Not found")
    
    # Close the connection
    conn.close()

if __name__ == "__main__":
    import asyncio
    
    # Run tests first
    print("=== Running Tests ===")
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
    
    # Then run the example
    print("\n=== Starting Example ===")
    asyncio.run(main())
