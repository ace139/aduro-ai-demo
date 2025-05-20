"""
Profile Updater Agent for updating user profile information in the database.

This module provides the ProfileUpdater agent which is responsible for:
- Validating and updating user profile fields
- Ensuring data integrity through validation rules
- Providing clear feedback on update operations
"""

import re
import sqlite3
from typing import Dict, Any, Optional, Literal, TypedDict
from pathlib import Path
from datetime import datetime

from agents import Agent, function_tool

# Constants
DB_PATH = Path(__file__).resolve().parent.parent / "db" / "users.db"

# Type Definitions
DietaryPreference = Literal["vegetarian", "non-vegetarian", "vegen"]

class UserProfile(TypedDict):
    """Represents a user's profile information."""
    first_name: str
    last_name: str
    city: str
    email: str
    date_of_birth: str  # YYYY-MM-DD format
    dietary_preference: Optional[DietaryPreference]
    medical_conditions: Optional[str]
    physical_limitations: Optional[str]

# Allowed profile fields and their validation rules
ALLOWED_FIELDS = {
    "first_name": {
        "type": str,
        "required": True,
        "validator": lambda x: bool(x.strip()) and len(x.strip()) >= 2,
        "error": "First name must be at least 2 characters long"
    },
    "last_name": {
        "type": str,
        "required": True,
        "validator": lambda x: bool(x.strip()) and len(x.strip()) >= 2,
        "error": "Last name must be at least 2 characters long"
    },
    "city": {
        "type": str,
        "required": True,
        "validator": lambda x: bool(x.strip()) and len(x.strip()) >= 2,
        "error": "City must be at least 2 characters long"
    },
    "email": {
        "type": str,
        "required": True,
        "validator": lambda x: bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', x)),
        "error": "Please enter a valid email address"
    },
    "date_of_birth": {
        "type": str,
        "required": True,
        "validator": lambda x: bool(re.match(r'^\d{4}-\d{2}-\d{2}$', x)) and \
                              bool(datetime.strptime(x, '%Y-%m-%d')),
        "error": "Please enter a valid date in YYYY-MM-DD format"
    },
    "dietary_preference": {
        "type": str,
        "required": False,
        "validator": lambda x: x.lower() in ['vegetarian', 'non-vegetarian', 'vegan'],
        "error": "Dietary preference must be one of: vegetarian, non-vegetarian, vegan"
    },
    "medical_conditions": {
        "type": str,
        "required": False,
        "validator": lambda x: True,  # No validation for free text
        "error": ""
    },
    "physical_limitations": {
        "type": str,
        "required": False,
        "validator": lambda x: True,  # No validation for free text
        "error": ""
    }
}

def validate_field_value(field_name: str, field_value: str) -> tuple[bool, str]:
    """
    Validate a field value against its rules.
    
    Args:
        field_name: Name of the field to validate
        field_value: Value to validate
        
    Returns:
        Tuple of (is_valid, validated_value_or_error_message)
    """
    if field_name not in ALLOWED_FIELDS:
        return False, f"Invalid field: {field_name}"
    
    field_info = ALLOWED_FIELDS[field_name]
    
    # Check if the field is required and has a value
    if field_info["required"] and not field_value:
        return False, f"{field_name.replace('_', ' ').title()} is required"
    
    # Convert the value to the correct type
    try:
        if field_value is not None:
            field_value = str(field_value).strip()
            if not field_value and not field_info["required"]:
                return True, None  # Empty but not required
    except (ValueError, TypeError) as e:
        return False, f"Invalid value for {field_name.replace('_', ' ')}: {str(e)}"
    
    # Run the validator if one exists
    if field_info["validator"] and field_value:
        try:
            if not field_info["validator"](field_value):
                return False, field_info["error"] or f"Invalid value for {field_name}"
        except Exception as e:
            return False, f"Validation error for {field_name}: {str(e)}"
    
    return True, field_value

# Internal function to handle the actual database update
async def _update_user_profile_impl(
    user_id: int, 
    field_name: str, 
    field_value: str,
    test_conn: Any = None
) -> Dict[str, Any]:
    """
    Internal implementation of update_user_profile that can handle test connections.
    
    Args:
        user_id: ID of the user to update
        field_name: Name of the field to update
        field_value: New value for the field
        test_conn: Optional database connection for testing
        
    Returns:
        Dictionary containing success status and message
    """
    # Validate the field name
    if field_name not in ALLOWED_FIELDS:
        return {
            "success": False,
            "message": f"Invalid field name: {field_name}",
            "field": field_name,
            "user_id": user_id
        }
    
    # Clean and validate the field value
    if field_value is not None:
        field_value = str(field_value).strip()
    
    is_valid, validation_result = validate_field_value(field_name, field_value)
    if not is_valid:
        return {
            "success": False,
            "message": validation_result,
            "field": field_name,
            "user_id": user_id
        }
    
    # If the value is empty and not required, set it to NULL
    if not validation_result and not ALLOWED_FIELDS[field_name]["required"]:
        validation_result = None
    
    # Update the database
    close_conn = False
    if test_conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        close_conn = True
    else:
        conn = test_conn
    
    try:
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return {
                "success": False,
                "message": f"User with ID {user_id} not found",
                "field": field_name,
                "user_id": user_id
            }
        
        # Update the field
        if validation_result is None:
            cursor.execute(
                f"UPDATE users SET {field_name} = NULL WHERE id = ?",
                (user_id,)
            )
        else:
            cursor.execute(
                f"UPDATE users SET {field_name} = ? WHERE id = ?",
                (validation_result, user_id)
            )
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"Successfully updated {field_name.replace('_', ' ')} for user {user_id}",
            "field": field_name,
            "user_id": user_id,
            "value": validation_result
        }
        
    except sqlite3.Error as e:
        return {
            "success": False,
            "message": f"Database error: {str(e)}",
            "field": field_name,
            "user_id": user_id
        }
    finally:
        if close_conn and conn:
            conn.close()

@function_tool
def update_user_profile(
    user_id: int, 
    field_name: str, 
    field_value: str
) -> Dict[str, Any]:
    """
    Updates a single profile field for the given user.
    
    Args:
        user_id: ID of the user to update
        field_name: Name of the field to update
        field_value: New value for the field
        
    Returns:
        Dictionary containing success status and message
    """
    return _update_user_profile_impl(user_id, field_name, field_value)

class ProfileUpdater(Agent):
    """Agent responsible for updating user profile information."""
    
    def __init__(self):
        super().__init__(
            name="profile_updater",
            instructions="""You are a helpful assistant that updates user profile information. 
            When given a user message and a field to update, you'll validate the input and update the database.
            Always confirm successful updates or provide clear error messages.
            
            Available fields that can be updated:
            - first_name: User's first name (required, min 2 chars)
            - last_name: User's last name (required, min 2 chars)
            - city: User's city (required, min 2 chars)
            - email: User's email address (must be valid format)
            - date_of_birth: User's date of birth (YYYY-MM-DD format)
            - dietary_preference: One of: vegetarian, non-vegetarian, vegan
            - medical_conditions: Any medical conditions (free text)
            - physical_limitations: Any physical limitations (free text)""",
            tools=[update_user_profile]
        )
    
    async def process_input(self, message: str, context: Dict[str, Any], test_conn=None) -> str:
        """
        Process user input to update a profile field.
        
        Args:
            message: User's message containing the field value
            context: Must contain 'user_id' and 'field_to_update'
            test_conn: Optional database connection for testing
            
        Returns:
            Confirmation message or error message
        """
        # Validate required context
        if 'user_id' not in context:
            return "Error: Missing user_id in context"
            
        if 'field_to_update' not in context:
            return "Error: Missing field_to_update in context"
        
        user_id = context['user_id']
        field_name = context['field_to_update']
        
        # Clean the input
        field_value = message.strip() if message else None
        
        # Special handling for dietary preference
        if field_name == 'dietary_preference' and field_value:
            field_value = field_value.lower()
            if field_value in ['veg', 'vegetarian']:
                field_value = 'vegetarian'
            elif field_value in ['non-veg', 'non veg', 'nonvegetarian']:
                field_value = 'non-vegetarian'
        
        # Call the internal implementation directly with test_conn
        result = await _update_user_profile_impl(
            user_id=user_id,
            field_name=field_name,
            field_value=field_value,
            test_conn=test_conn
        )
        
        return result.get("message", "An unknown error occurred")
        """Set up test database and agent."""
        # Use an in-memory database for testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        
        # Create the users table
        self.conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            city TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            date_of_birth DATE NOT NULL,
            dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
            medical_conditions TEXT,
            physical_limitations TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Insert a test user
        self.conn.execute("""
        INSERT INTO users (id, first_name, last_name, city, email, date_of_birth)
        VALUES (1, 'Test', 'User', 'Test City', 'test@example.com', '1990-01-01')
        """)
        self.conn.commit()
        
        # Create the agent
        self.agent = ProfileUpdater()
    
    def tearDown(self):
        """Clean up after tests."""
        self.conn.close()
    
    async def test_update_dietary_preference(self):
        """Test updating dietary preference to a valid value."""
        # Test with valid dietary preference
        result = await self.agent.process_input(
            "I'm vegan",
            {"user_id": 1, "field_to_update": "dietary_preference"}
        )
        self.assertIn("Successfully updated dietary preference", result)
        
        # Verify the update in the database
        cursor = self.conn.cursor()
        cursor.execute("SELECT dietary_preference FROM users WHERE id = 1")
        row = cursor.fetchone()
        self.assertEqual(row[0], "vegan")
    
    async def test_invalid_dietary_preference(self):
        """Test updating dietary preference to an invalid value."""
        result = await self.agent.process_input(
            "I only eat fruit",
            {"user_id": 1, "field_to_update": "dietary_preference"}
        )
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("must be one of: vegetarian, non-vegetarian, vegan", result)
    
    async def test_missing_field_to_update(self):
        """Test with missing field_to_update in context."""
        result = await self.agent.process_input(
            "I'm vegan",
            {"user_id": 1}  # Missing field_to_update
        )
        self.assertEqual(result, "Error: Missing field_to_update in context")
    
    async def test_update_email(self):
        """Test updating email address with validation."""
        # Test with valid email
        result = await self.agent.process_input(
            "new.email@example.com",
            {"user_id": 1, "field_to_update": "email"}
        )
        self.assertIn("Successfully updated email", result)
        
        # Test with invalid email
        result = await self.agent.process_input(
            "not-an-email",
            {"user_id": 1, "field_to_update": "email"}
        )
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("valid email address", result)

if __name__ == "__main__":
    import asyncio
    
    async def main():
        """Run the agent with example usage."""
        # Create a test database connection
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        
        # Create the users table if it doesn't exist
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # Insert a test user
        cursor.execute("""
        INSERT INTO users (id, first_name, last_name, city, email, date_of_birth)
        VALUES (1, 'Test', 'User', 'Test City', 'test@example.com', '1990-01-01')
        """)
        conn.commit()
        
        updater = ProfileUpdater()
        
        # Example 1: Update dietary preference with valid value
        print("\n=== Example 1: Update Dietary Preference ===")
        result = await updater.process_input(
            "vegetarian",
            {"user_id": 1, "field_to_update": "dietary_preference"}
        )
        print(f"Result: {result}")
        
        # Example 2: Update email with valid value
        print("\n=== Example 2: Update Email ===")
        result = await updater.process_input(
            "new.email@example.com",
            {"user_id": 1, "field_to_update": "email"}
        )
        print(f"Result: {result}")
        
        # Example 3: Try invalid dietary preference
        print("\n=== Example 3: Invalid Dietary Preference ===")
        result = await updater.process_input(
            "fruitarian",
            {"user_id": 1, "field_to_update": "dietary_preference"}
        )
        print(f"Result: {result}")
        
        # Example 4: Missing field_to_update
        print("\n=== Example 4: Missing Field ===")
        result = await updater.process_input(
            "Some value",
            {"user_id": 1}  # Missing field_to_update
        )
        print(f"Result: {result}")
        
        # Clean up
        conn.close()
    
    # Run the example
    asyncio.run(main())
