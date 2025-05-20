"""
Tests for the ProfileUpdater agent.
"""

import pytest
import sqlite3

from aduro_agents.profile_updater import (
    ProfileUpdater,
    validate_field_value,
    _update_user_profile_impl
)

# Test data
TEST_USER_ID = 1
TEST_PROFILE = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "date_of_birth": "1990-01-01",
    "city": "Test City",
    "dietary_preference": "vegetarian"
}

# Fixtures
@pytest.fixture
def test_db():
    """Set up an in-memory database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    # Create tables
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            date_of_birth TEXT NOT NULL,
            city TEXT NOT NULL,
            dietary_preference TEXT,
            medical_conditions TEXT,
            physical_limitations TEXT
        )
    """)
    
    # Insert test user
    cursor.execute(
        """
        INSERT INTO users (
            id, first_name, last_name, email, date_of_birth, city, dietary_preference
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            TEST_USER_ID,
            TEST_PROFILE["first_name"],
            TEST_PROFILE["last_name"],
            TEST_PROFILE["email"],
            TEST_PROFILE["date_of_birth"],
            TEST_PROFILE["city"],
            TEST_PROFILE["dietary_preference"]
        )
    )
    conn.commit()
    
    yield conn
    conn.close()

@pytest.fixture
def profile_updater():
    """Create a ProfileUpdater instance for testing."""
    return ProfileUpdater()

# Tests
class TestProfileUpdater:
    """Tests for the ProfileUpdater agent."""
    
    @pytest.mark.asyncio
    async def test_validate_field_value_valid(self):
        """Test validating valid field values."""
        # Test valid first name
        is_valid, result = validate_field_value("first_name", "John")
        assert is_valid is True
        assert result == "John"
        
        # Test valid email
        is_valid, result = validate_field_value("email", "test@example.com")
        assert is_valid is True
        assert result == "test@example.com"
        
        # Test valid date of birth
        is_valid, result = validate_field_value("date_of_birth", "2000-01-01")
        assert is_valid is True
        assert result == "2000-01-01"
        
        # Test valid dietary preference
        is_valid, result = validate_field_value("dietary_preference", "vegetarian")
        assert is_valid is True
        assert result == "vegetarian"
    
    @pytest.mark.asyncio
    async def test_validate_field_value_invalid(self):
        """Test validating invalid field values."""
        # Test invalid first name (too short)
        is_valid, result = validate_field_value("first_name", "J")
        assert is_valid is False
        assert "First name must be at least 2 characters long" in result
        
        # Test invalid email
        is_valid, result = validate_field_value("email", "not-an-email")
        assert is_valid is False
        assert "Please enter a valid email address" in result
        
        # Test invalid date of birth
        is_valid, result = validate_field_value("date_of_birth", "not-a-date")
        assert is_valid is False
        assert "Please enter a valid date in YYYY-MM-DD format" in result
        
        # Test invalid dietary preference
        is_valid, result = validate_field_value("dietary_preference", "invalid-preference")
        assert is_valid is False
        assert "must be one of: vegetarian, non-vegetarian, vegan" in result
    
    @pytest.mark.asyncio
    async def test_update_user_profile_success(self, test_db):
        """Test successfully updating a user profile field."""
        # Test updating city
        result = await _update_user_profile_impl(
            user_id=TEST_USER_ID,
            field_name="city",
            field_value="New City",
            test_conn=test_db
        )
        
        assert result["success"] is True
        assert "Successfully updated city for user" in result["message"]
        assert result["field"] == "city"
        assert result["value"] == "New City"
        
        # Verify the update in the database
        cursor = test_db.cursor()
        cursor.execute("SELECT city FROM users WHERE id = ?", (TEST_USER_ID,))
        assert cursor.fetchone()["city"] == "New City"
    
    @pytest.mark.asyncio
    async def test_update_user_profile_invalid_field(self, test_db):
        """Test updating with an invalid field name."""
        result = await _update_user_profile_impl(
            user_id=TEST_USER_ID,
            field_name="invalid_field",
            field_value="some value",
            test_conn=test_db
        )
        
        assert result["success"] is False
        assert "Invalid field name" in result["message"]
    
    @pytest.mark.asyncio
    async def test_update_user_profile_invalid_value(self, test_db):
        """Test updating with an invalid field value."""
        result = await _update_user_profile_impl(
            user_id=TEST_USER_ID,
            field_name="email",
            field_value="not-an-email",
            test_conn=test_db
        )
        
        assert result["success"] is False
        assert "Please enter a valid email address" in result["message"]
    
    @pytest.mark.asyncio
    async def test_process_input_success(self, profile_updater, test_db):
        """Test the process_input method with valid input."""
        context = {
            "user_id": TEST_USER_ID,
            "field_to_update": "city"
        }
        
        result = await profile_updater.process_input(
            "New City",
            context,
            test_conn=test_db
        )
        
        assert "Successfully updated city" in result
    
    @pytest.mark.asyncio
    async def test_process_input_missing_context(self, profile_updater):
        """Test process_input with missing required context."""
        # Missing user_id
        result = await profile_updater.process_input(
            "New City",
            {"field_to_update": "city"}
        )
        assert "Missing user_id" in result
        
        # Missing field_to_update
        result = await profile_updater.process_input(
            "New City",
            {"user_id": TEST_USER_ID}
        )
        assert "Missing field_to_update" in result
    
    @pytest.mark.asyncio
    async def test_process_input_dietary_preference_variations(self, profile_updater, test_db):
        """Test processing different variations of dietary preference input."""
        variations = [
            ("veg", "vegetarian"),
            ("VEGETARIAN", "vegetarian"),
            ("non-veg", "non-vegetarian"),
            ("non veg", "non-vegetarian"),
            ("vegan", "vegan")
        ]
        
        for input_val, expected in variations:
            context = {
                "user_id": TEST_USER_ID,
                "field_to_update": "dietary_preference"
            }
            
            result = await profile_updater.process_input(
                input_val,
                context,
                test_conn=test_db
            )
            
            assert "Successfully updated dietary preference" in result
            
            # Verify the value in the database
            cursor = test_db.cursor()
            cursor.execute(
                "SELECT dietary_preference FROM users WHERE id = ?",
                (TEST_USER_ID,)
            )
            db_value = cursor.fetchone()["dietary_preference"]
            assert db_value == expected
