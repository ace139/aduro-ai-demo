"""
Orchestrator Agent to coordinate between the different specialized agents.
This manages the flow between profile collection, CGM readings, and meal planning.
"""

import asyncio
import contextlib
import logging
import sqlite3
import os
import pytest
from pathlib import Path
from typing import Dict, Any, Optional, TypedDict, Protocol

# Import Aduro AI custom agents from the new package
from aduro_agents.greeter_profiler import GreeterProfiler
from aduro_agents.profile_updater import ProfileUpdater
from aduro_agents.cgm_collector import CGMCollector
from aduro_agents.meal_planner import MealPlanner

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type aliases
UserID = int
ProfileData = Dict[str, Any]
AgentResponse = str

class DatabaseConfig(TypedDict):
    """Database configuration settings."""
    db_path: str
    timeout: float
    detect_types: int
    isolation_level: Optional[str]
    check_same_thread: bool

class DatabaseConnection(Protocol):
    """Protocol for database connections."""
    def cursor(self) -> sqlite3.Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> 'DatabaseConnection': ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

DEFAULT_DB_CONFIG: DatabaseConfig = {
    'db_path': os.getenv('DB_PATH', 'db/users.db'),
    'timeout': 30.0,
    'detect_types': sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    'isolation_level': 'IMMEDIATE',
    'check_same_thread': False,
}

class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    pass

class DatabaseError(OrchestratorError):
    """Database related errors."""
    pass

class ValidationError(OrchestratorError):
    """Validation related errors."""
    pass

class Orchestrator:
    """
    Orchestrator agent that coordinates between other specialized agents.
    
    The orchestrator maintains a stateless architecture, with all state being 
    carried in the context dictionary passed to handle_message.
    """
    
    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        """Initialize the orchestrator with all sub-agents and database configuration.
        
        Args:
            db_config: Database configuration dictionary. If None, uses defaults.
        """
        self.db_config = db_config or DEFAULT_DB_CONFIG
        
        # Ensure database directory exists
        db_path = Path(self.db_config['db_path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize all sub-agents with database configuration
        self.greeter_profiler = GreeterProfiler()
        self.profile_updater = ProfileUpdater()
        self.cgm_collector = CGMCollector()
        self.meal_planner = MealPlanner()
        
        # Initialize database schema if needed
        self._init_db()
    
    @contextlib.contextmanager
    def _get_db_connection(self) -> DatabaseConnection:
        """Get a database connection with automatic cleanup."""
        conn = None
        try:
            conn = sqlite3.connect(
                database=self.db_config['db_path'],
                timeout=self.db_config['timeout'],
                detect_types=self.db_config['detect_types'],
                isolation_level=self.db_config['isolation_level'],
                check_same_thread=self.db_config['check_same_thread']
            )
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise DatabaseError(f"Database operation failed: {e}") from e
        finally:
            if conn:
                conn.close()
    
    def _init_db(self) -> None:
        """Initialize database schema if it doesn't exist."""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create users table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT,
                    last_name TEXT,
                    city TEXT,
                    email TEXT UNIQUE,
                    date_of_birth DATE,
                    dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create cgm_readings table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cgm_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reading_value REAL NOT NULL,
                    reading_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            conn.commit()
    
    async def handle_message(self, message: str, context: Dict[str, Any]) -> str:
        """
        Process an incoming message and route it to the appropriate agent.
        
        Args:
            message: The raw user text
            context: Dictionary carrying state and user information
                Must have user_id: int
                May have profile_complete: bool
                May have awaiting_profile_field: bool
                May have field_to_update: str
                May have cgm_collected: bool
                May have awaiting_cgm: bool
                
        Returns:
            Response from the appropriate agent
            
        Raises:
            ValidationError: If required context is missing or invalid
        """
        try:
            # 1. Authenticate - validate user_id exists
            if 'user_id' not in context or not isinstance(context.get('user_id'), int):
                raise ValidationError("Missing or invalid user ID. Please re-authenticate.")
            
            user_id = context['user_id']
            
            # 2. Profile Phase - ensure profile is complete
            if not context.get("profile_complete", False):
                return await self._handle_profile_phase(message, context, user_id)
            
            # 3. CGM Phase - collect CGM readings if needed
            if not context.get("cgm_collected", False):
                return await self._handle_cgm_phase(message, context)
            
            # 4. Meal Planning Phase - generate meal plan
            return await self._handle_meal_planning_phase(message, context, user_id)
            
        except ValidationError as e:
            logger.warning(f"Validation error: {e}")
            return f"⚠️ {str(e)}"
        except DatabaseError as e:
            logger.error(f"Database error: {e}")
            return "⚠️ An error occurred while accessing your data. Please try again later."
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return "⚠️ An unexpected error occurred. Our team has been notified."
    
    async def _handle_profile_phase(self, message: str, context: Dict[str, Any], user_id: int) -> str:
        """Handle the profile collection phase."""
        # If awaiting a specific profile field, use the profile updater
        if context.get("awaiting_profile_field", False) and "field_to_update" in context:
            return await self._handle_profile_field_update(message, context, user_id)
        
        # Otherwise, use the greeter profiler to get/validate the profile
        response = await self.greeter_profiler.process_input(message, context)
        
        # Check if we need specific profile fields after this
        profile_complete = await self._check_profile_complete(user_id)
        if profile_complete:
            context["profile_complete"] = True
            response += "\n\nYour profile is now complete! Let's collect your CGM readings next."
        else:
            # If profile is incomplete, set flag for next field
            context["awaiting_profile_field"] = True
            next_field = await self._get_next_missing_field(user_id)
            if next_field:
                context["field_to_update"] = next_field
                response += f"\n\nWhat's your {next_field.replace('_', ' ')}?"
        
        return response
    
    async def _handle_profile_field_update(self, message: str, context: Dict[str, Any], user_id: int) -> str:
        """Handle updating a specific profile field."""
        response = await self.profile_updater.process_input(message, context)
        
        # If the update was successful, reset the awaiting flag
        if not response.startswith("Error:"):
            context["awaiting_profile_field"] = False
            
            # Check if profile is now complete
            profile_complete = await self._check_profile_complete(user_id)
            if profile_complete:
                context["profile_complete"] = True
                response += "\n\nYour profile is now complete! Let's collect your CGM readings next."
            else:
                # Determine the next missing field
                next_field = await self._get_next_missing_field(user_id)
                if next_field:
                    context["awaiting_profile_field"] = True
                    context["field_to_update"] = next_field
                    response += f"\n\nWhat's your {next_field.replace('_', ' ')}?"
        
        return response
    
    async def _handle_cgm_phase(self, message: str, context: Dict[str, Any]) -> str:
        """Handle the CGM data collection phase."""
        # If awaiting CGM readings specifically
        if context.get("awaiting_cgm", False):
            response = await self.cgm_collector.process_input(message, context)
            
            # Check if we have collected valid CGM readings
            if any(term in response.lower() for term in ["success", "thank", "received"]):
                context["cgm_collected"] = True
                context["awaiting_cgm"] = False
                response += "\n\nNow that we have your CGM readings, I can create a personalized meal plan for you. Type 'plan' to generate your meal plan."
        else:
            # Start the CGM collection process
            response = await self.cgm_collector.process_input("start", context)
            context["awaiting_cgm"] = True
        
        return response
    
    async def _handle_meal_planning_phase(self, message: str, context: Dict[str, Any], user_id: int) -> str:
        """Handle the meal planning phase."""
        try:
            # First try using process_input if available
            if hasattr(self.meal_planner, 'process_input'):
                return await self.meal_planner.process_input(message, context)
            
            # Fall back to generate_meal_plan if process_input is not available
            if hasattr(self.meal_planner, 'generate_meal_plan'):
                meal_plan = await self.meal_planner.generate_meal_plan(user_id)
                return f"Your personalized meal plan:\n\n{meal_plan}"
            
            # If neither method is available
            return "Your meal plan will be generated based on your profile and CGM readings. This feature is coming soon!"
            
        except Exception as e:
            logger.error(f"Meal planning error: {e}", exc_info=True)
            return "I'm having trouble generating your meal plan right now. Please try again later."
    
    async def _check_profile_complete(self, user_id: int) -> bool:
        """
        Check if the user profile has all required fields.
        
        Args:
            user_id: User ID to check
            
        Returns:
            True if profile is complete, False otherwise
            
        Raises:
            DatabaseError: If there's an error accessing the database
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get user profile
                cursor.execute("""
                    SELECT first_name, last_name, city, email, date_of_birth, dietary_preference
                    FROM users
                    WHERE id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if not row:
                    return False
                
                # Check required fields
                required_fields = ["first_name", "last_name", "city", "email", "date_of_birth", "dietary_preference"]
                return all(row[field] for field in required_fields)
                
        except sqlite3.Error as e:
            logger.error(f"Error checking profile completeness: {e}")
            raise DatabaseError("Failed to check profile completeness") from e
    
    async def _get_next_missing_field(self, user_id: int) -> str:
        """
        Get the next missing field for a user profile.
        
        Args:
            user_id: User ID to check
            
        Returns:
            Field name of next missing field or empty string if none
            
        Raises:
            DatabaseError: If there's an error accessing the database
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get user profile
                cursor.execute("""
                    SELECT first_name, last_name, city, email, date_of_birth, dietary_preference
                    FROM users
                    WHERE id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if not row:
                    return ""
                
                # Check fields in order of importance
                required_fields = ["first_name", "last_name", "city", "email", "date_of_birth", "dietary_preference"]
                for field in required_fields:
                    if not row[field]:
                        return field
                
                return ""
                
        except sqlite3.Error as e:
            logger.error(f"Error getting next missing field: {e}")
            raise DatabaseError("Failed to get next missing field") from e


# Test fixtures
@pytest.fixture
def test_db():
    """Set up a test database with sample data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    # Create the users table
    conn.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # Insert test users
    conn.execute("""
    INSERT INTO users (id, first_name, last_name, city, email, date_of_birth, dietary_preference)
    VALUES (1, 'Test', 'User', 'Test City', 'test@example.com', '1990-01-01', 'vegetarian')
    """)
    
    # Insert an incomplete user
    conn.execute("""
    INSERT INTO users (id, first_name, email)
    VALUES (2, 'Incomplete', 'incomplete@example.com')
    """)
    
    conn.commit()
    yield conn
    conn.close()

@pytest.fixture
def orchestrator(test_db):
    """Create an orchestrator instance with the test database."""
    # Create a custom DB config that uses our in-memory connection
    db_config = {
        'db_path': ":memory:",
        'timeout': 30.0,
        'detect_types': sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        'isolation_level': 'IMMEDIATE',
        'check_same_thread': False
    }
    return Orchestrator(db_config=db_config)

# Tests
class TestOrchestrator:
    """Tests for the Orchestrator agent."""
    
    @pytest.mark.asyncio
    async def test_invalid_user(self, orchestrator):
        """Test with an invalid user (missing user_id)."""
        # Test missing user_id
        context = {}
        response = await orchestrator.handle_message("hello", context)
        assert "Missing or invalid user ID" in response
        
        # Test non-integer user_id
        context = {"user_id": "invalid"}
        response = await orchestrator.handle_message("hello", context)
        assert "Missing or invalid user ID" in response
    
    @pytest.mark.asyncio
    async def test_full_new_user_flow(self, orchestrator):
        """Test the full flow for a new user."""
        # TODO: This would be a more complex test that simulates the entire flow
        # Requires mocking the sub-agents to respond predictably
        pass
    
    @pytest.mark.asyncio
    async def test_skip_to_meal_plan(self, orchestrator):
        """Test skipping to meal plan with a complete profile and CGM readings."""
        # TODO: This would skip directly to meal planning
        # Requires mocking the MealPlanner to respond predictably
        pass


async def main():
    """Run example usage of the orchestrator."""
    orchestrator = Orchestrator()
    
    # Example 1: Authentication error
    print("\n=== Example 1: Authentication Error ===")
    response = await orchestrator.handle_message("Hello", {})
    print(f"Response: {response}")
    
    # Example 2: Start with a valid user_id
    print("\n=== Example 2: Start with Valid User ID ===")
    context = {"user_id": 2}  # This user is in the database but has an incomplete profile
    response = await orchestrator.handle_message("Hello", context)
    print(f"Response: {response}")
    print(f"Updated context: {context}")
    
    # Example 3: Skip to meal planning
    print("\n=== Example 3: Skip to Meal Planning ===")
    context = {"user_id": 1, "profile_complete": True, "cgm_collected": True}
    response = await orchestrator.handle_message("I want a meal plan", context)
    print(f"Response: {response}")


if __name__ == "__main__":
    # Run example usage
    asyncio.run(main())
