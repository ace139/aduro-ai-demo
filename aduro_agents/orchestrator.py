"""
Orchestrator Agent to coordinate between the different specialized agents.
This manages the flow between profile collection, CGM readings, and meal planning.
"""

import asyncio
import unittest
import sqlite3
from pathlib import Path
from typing import Dict, Any

# Import Aduro AI custom agents from the new package
from aduro_agents.greeter_profiler import GreeterProfiler
from aduro_agents.profile_updater import ProfileUpdater
from aduro_agents.cgm_collector import CGMCollector
from aduro_agents.meal_planner import MealPlanner

# Database constants
DB_PATH = Path("db/users.db")

class Orchestrator:
    """
    Orchestrator agent that coordinates between other specialized agents.
    
    The orchestrator maintains a stateless architecture, with all state being 
    carried in the context dictionary passed to handle_message.
    """
    
    def __init__(self):
        """Initialize the orchestrator with all sub-agents."""
        # Initialize all sub-agents
        self.greeter_profiler = GreeterProfiler()
        self.profile_updater = ProfileUpdater()
        self.cgm_collector = CGMCollector()
        self.meal_planner = MealPlanner()
    
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
        """
        # 1. Authenticate - validate user_id exists
        if 'user_id' not in context or not isinstance(context.get('user_id'), int):
            return "⚠️ Missing or invalid user ID. Please re-authenticate."
        
        # 2. Profile Phase - ensure profile is complete
        if not context.get("profile_complete", False):
            # If awaiting a specific profile field, use the profile updater
            if context.get("awaiting_profile_field", False) and "field_to_update" in context:
                response = await self.profile_updater.process_input(message, context)
                
                # If the update was successful, reset the awaiting flag
                if not response.startswith("Error:"):
                    context["awaiting_profile_field"] = False
                    
                    # Check if profile is now complete
                    profile_complete = await self._check_profile_complete(context["user_id"])
                    if profile_complete:
                        context["profile_complete"] = True
                        response += "\n\nYour profile is now complete! Let's collect your CGM readings next."
                    else:
                        # Determine the next missing field
                        next_field = await self._get_next_missing_field(context["user_id"])
                        if next_field:
                            context["awaiting_profile_field"] = True
                            context["field_to_update"] = next_field
                            response += f"\n\nWhat's your {next_field.replace('_', ' ')}?"
                
                return response
            
            # Otherwise, use the greeter profiler to get/validate the profile
            response = await self.greeter_profiler.process_input(message, context)
            
            # Check if we need specific profile fields after this
            profile_complete = await self._check_profile_complete(context["user_id"])
            if profile_complete:
                context["profile_complete"] = True
            else:
                # If profile is incomplete, set flag for next field
                context["awaiting_profile_field"] = True
                next_field = await self._get_next_missing_field(context["user_id"])
                if next_field:
                    context["field_to_update"] = next_field
            
            return response
        
        # 3. CGM Phase - collect CGM readings if needed
        if not context.get("cgm_collected", False):
            # If awaiting CGM readings specifically
            if context.get("awaiting_cgm", False):
                response = await self.cgm_collector.process_input(message, context)
                
                # Check if we have collected valid CGM readings
                if "success" in response.lower() or "thank" in response.lower():
                    context["cgm_collected"] = True
                    context["awaiting_cgm"] = False
                    response += "\n\nNow that we have your CGM readings, I can create a personalized meal plan for you. Type 'plan' to generate your meal plan."
            else:
                # Start the CGM collection process
                response = await self.cgm_collector.process_input("start", context)
                context["awaiting_cgm"] = True
            
            return response
        
        # 4. Meal Planning Phase - generate meal plan
        # MealPlanner might not have process_input implemented yet
        # Use a fallback approach to handle this case
        try:
            if hasattr(self.meal_planner, 'process_input'):
                response = await self.meal_planner.process_input(message, context)
            else:
                # If the MealPlanner doesn't have process_input, call generate_meal_plan directly
                response = await self.meal_planner.generate_meal_plan(context['user_id'])
                response = f"Your personalized meal plan:\n\n{response}"
            return response
        except AttributeError:
            # Fallback response if meal planner is not fully implemented
            return "Your meal plan will be generated based on your profile and CGM readings. This feature is coming soon!"
    
    async def _check_profile_complete(self, user_id: int) -> bool:
        """
        Check if the user profile has all required fields.
        
        Args:
            user_id: User ID to check
            
        Returns:
            True if profile is complete, False otherwise
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
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
            for field in required_fields:
                if not row[field]:
                    return False
            
            return True
        except sqlite3.Error:
            return False
        finally:
            if conn:
                conn.close()
    
    async def _get_next_missing_field(self, user_id: int) -> str:
        """
        Get the next missing field for a user profile.
        
        Args:
            user_id: User ID to check
            
        Returns:
            Field name of next missing field or empty string if none
        """
        try:
            # Connect to the database
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
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
        except sqlite3.Error:
            return ""
        finally:
            if conn:
                conn.close()


class TestOrchestrator(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the Orchestrator agent."""
    
    def setUp(self):
        """Set up test database and orchestrator."""
        # Use an in-memory database for testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        
        # Create the users table
        self.conn.execute("""
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
        self.conn.execute("""
        INSERT INTO users (id, first_name, last_name, city, email, date_of_birth, dietary_preference)
        VALUES (1, 'Test', 'User', 'Test City', 'test@example.com', '1990-01-01', 'vegetarian')
        """)
        
        # Insert an incomplete user
        self.conn.execute("""
        INSERT INTO users (id, first_name, email)
        VALUES (2, 'Incomplete', 'incomplete@example.com')
        """)
        
        self.conn.commit()
        
        # Create the orchestrator
        self.orchestrator = Orchestrator()
        
        # Mock the database path
        # Note: In a real environment, you'd use a more sophisticated mocking approach
        # This is a simple example for demonstration
        global DB_PATH
        DB_PATH = ":memory:"
    
    def tearDown(self):
        """Clean up after tests."""
        self.conn.close()
    
    async def test_invalid_user(self):
        """Test with an invalid user (missing user_id)."""
        context = {}
        response = await self.orchestrator.handle_message("hello", context)
        self.assertEqual(response, "⚠️ Missing or invalid user ID. Please re-authenticate.")
        
        # Try with non-integer user_id
        context = {"user_id": "invalid"}
        response = await self.orchestrator.handle_message("hello", context)
        self.assertEqual(response, "⚠️ Missing or invalid user ID. Please re-authenticate.")
    
    async def test_full_new_user_flow(self):
        """Test the full flow for a new user."""
        # TODO: This would be a more complex test that simulates the entire flow
        # Requires mocking the sub-agents to respond predictably
        pass
    
    async def test_skip_to_meal_plan(self):
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
